//! Formal proofs of memgate's Cedar policies with Cedar's symbolic compiler (SymCC).
//!
//!     CVC5=../.tools/cvc5-macOS-arm64-static/bin/cvc5 cargo run --release
//!
//! Each guarantee is written as a Cedar "property" policy set. SymCC proves, for every request and
//! every entity store the schema allows, that whatever memgate's policies allow the property also
//! allows (implication), or that the two allow exactly the same requests (equivalence), and returns
//! a concrete counterexample when that fails. Results go to results.json.
//!
//! What is proved is the policies. The attributes they read (haLocs, carryTypes) are computed by
//! memgate in Python from the world, and SymCC treats them as arbitrary; the properties that depend
//! on them being computed correctly are marked, and their failures show exactly which invariant
//! the Python code has to keep.

use std::str::FromStr;

use cedar_policy::{PolicySet, Schema};
use cedar_policy_symcc::{solver::LocalSolver, CedarSymCompiler, CompiledPolicy, CompiledPolicySet};

const SCHEMA: &str = include_str!("../../src/memgate/policies/memgate.cedarschema");
const POLICIES: &str = include_str!("../../src/memgate/policies/memgate.cedar");

enum Check {
    /// memgate allows ⇒ the property allows
    Implies,
    /// memgate allows ⇔ the property allows
    Equivalent,
    /// memgate allows at least one request of this action
    NotAlwaysDenies,
}

struct Property {
    id: &'static str,
    action: &'static str,
    claim: &'static str,
    check: Check,
    policy: &'static str,
    /// Holds only if memgate computes the named attribute correctly (not provable in Cedar).
    assumes: Option<&'static str>,
}

fn properties() -> Vec<Property> {
    vec![
        // -- recall ---------------------------------------------------------------------------------
        Property { id: "R1-identity", action: "read", check: Check::Implies, assumes: None,
            claim: "A memory with an identity label is recalled only by that agent",
            policy: r#"permit (principal, action == Action::"read", resource) when { [principal].containsAll(resource.selfs) };"# },
        Property { id: "R2-location", action: "read", check: Check::Implies, assumes: None,
            claim: "A memory with a location label is recalled only in that location",
            policy: r#"permit (principal, action == Action::"read", resource) when { [context.location].containsAll(resource.locs) };"# },
        Property { id: "R3-participants", action: "read", check: Check::Implies, assumes: None,
            claim: "A memory with participant labels is recalled only by a participant",
            policy: r#"permit (principal, action == Action::"read", resource) when { resource.withs.isEmpty() || resource.withs.contains(principal) };"# },
        Property { id: "R4-seal", action: "read", check: Check::Implies, assumes: None,
            claim: "A memory formed in a high-assurance location is recalled only in that location",
            policy: r#"permit (principal, action == Action::"read", resource) when { [context.location].containsAll(resource.haLocs) };"# },
        Property { id: "R5-seal-by-location", action: "read", check: Check::Implies,
            assumes: Some("haLocs = the locations in locs whose highAssurance is true"),
            claim: "Outside a high-assurance location, nothing formed in a high-assurance location is recalled",
            policy: r#"permit (principal, action == Action::"read", resource) when { resource.haLocs.isEmpty() || context.location.highAssurance };"# },
        Property { id: "R6-read-spec", action: "read", check: Check::Equivalent, assumes: None,
            claim: "Recall is allowed exactly when R1–R4 all hold (no other way in, and nothing they allow is refused)",
            policy: r#"permit (principal, action == Action::"read", resource) when {
                [principal].containsAll(resource.selfs) && [context.location].containsAll(resource.locs) &&
                (resource.withs.isEmpty() || resource.withs.contains(principal)) &&
                [context.location].containsAll(resource.haLocs) };"# },
        Property { id: "R7-read-live", action: "read", check: Check::NotAlwaysDenies, assumes: None,
            claim: "Recall is possible at all (the policies are not vacuously safe)", policy: "" },
        // -- carry-out into personal memory ----------------------------------------------------------
        Property { id: "C1-no-high-assurance", action: "writePersonal", check: Check::Implies, assumes: None,
            claim: "Nothing formed in a high-assurance location is carried out",
            policy: r#"permit (principal, action == Action::"writePersonal", resource) when { resource.haLocs.isEmpty() };"# },
        Property { id: "C2-environments-allow", action: "writePersonal", check: Check::Implies,
            assumes: Some("carryTypes = the memory types every location's environment lets out"),
            claim: "A memory is carried out only if its type is one every source environment lets out",
            policy: r#"permit (principal, action == Action::"writePersonal", resource) when { resource.carryTypes.contains(context.memoryType) };"# },
        Property { id: "C3-carrier-had-access", action: "writePersonal", check: Check::Implies, assumes: None,
            claim: "Only an agent who holds the memory's identity and participant labels can carry it out",
            policy: r#"permit (principal, action == Action::"writePersonal", resource) when {
                [principal].containsAll(resource.selfs) && (resource.withs.isEmpty() || resource.withs.contains(principal)) };"# },
        Property { id: "C4-carry-where-readable", action: "writePersonal", check: Check::Implies, assumes: None,
            claim: "A memory is carried out only where its source is readable (the carrier is in every one of its locations)",
            policy: r#"permit (principal, action == Action::"writePersonal", resource) when { [context.location].containsAll(resource.locs) };"# },
        Property { id: "C5-carry-spec", action: "writePersonal", check: Check::Equivalent, assumes: None,
            claim: "Carry-out is allowed exactly when C1–C4 all hold",
            policy: r#"permit (principal, action == Action::"writePersonal", resource) when {
                [principal].containsAll(resource.selfs) && (resource.withs.isEmpty() || resource.withs.contains(principal)) &&
                [context.location].containsAll(resource.locs) &&
                resource.carryTypes.contains(context.memoryType) && resource.haLocs.isEmpty() };"# },
        Property { id: "C6-carry-live", action: "writePersonal", check: Check::NotAlwaysDenies, assumes: None,
            claim: "Carry-out is possible at all", policy: "" },
        // -- writes ----------------------------------------------------------------------------------
        Property { id: "W1-own-identity", action: "write", check: Check::Implies, assumes: None,
            claim: "No agent writes under another agent's identity label",
            policy: r#"permit (principal, action == Action::"write", resource) when { [principal].containsAll(resource.selfs) };"# },
        Property { id: "W2-writer-holds", action: "write", check: Check::Implies, assumes: None,
            claim: "A writer either writes under its own identity or is one of the participants",
            policy: r#"permit (principal, action == Action::"write", resource) when { !resource.selfs.isEmpty() || resource.withs.contains(principal) };"# },
        Property { id: "W3-write-place", action: "write", check: Check::Implies, assumes: None,
            claim: "A memory with a location label is written only in that location",
            policy: r#"permit (principal, action == Action::"write", resource) when { [context.location].containsAll(resource.locs) };"# },
        Property { id: "W4-write-seal", action: "write", check: Check::Implies, assumes: None,
            claim: "Anything written in a high-assurance location carries that location's label",
            policy: r#"permit (principal, action == Action::"write", resource) when { !context.location.highAssurance || resource.locs.contains(context.location) };"# },
        Property { id: "W5-write-spec", action: "write", check: Check::Equivalent, assumes: None,
            claim: "A write is allowed exactly when W1–W4 all hold",
            policy: r#"permit (principal, action == Action::"write", resource) when {
                [principal].containsAll(resource.selfs) && (!resource.selfs.isEmpty() || resource.withs.contains(principal)) &&
                [context.location].containsAll(resource.locs) &&
                (!context.location.highAssurance || resource.locs.contains(context.location)) };"# },
        Property { id: "W6-write-live", action: "write", check: Check::NotAlwaysDenies, assumes: None,
            claim: "Writing is possible at all", policy: "" },
    ]
}

#[tokio::main]
async fn main() {
    let (schema, _) = Schema::from_cedarschema_str(SCHEMA).expect("schema");
    let memgate = PolicySet::from_str(POLICIES).expect("policies");
    let mut symcc = CedarSymCompiler::new(LocalSolver::cvc5().expect("cvc5: set CVC5 to the solver's path")).unwrap();
    let mut results = Vec::new();
    let mut all_ok = true;

    // Every policy must never error (a Cedar error would skip the policy, which for a forbid means allowing).
    for env in schema.request_envs() {
        for p in memgate.policies() {
            let cp = CompiledPolicy::compile(p, &env, &schema).unwrap();
            let cex = symcc.check_never_errors_with_counterexample_opt(&cp).await.unwrap();
            let ok = cex.is_none();
            all_ok &= ok;
            let name = p.annotation("id").map(str::to_string).unwrap_or_else(|| p.id().to_string());
            let action = env.action().id().unescaped().to_string();
            println!("{name} never-errors [{action}]: {}", if ok { "PROVED" } else { "FAILED" });
            results.push(format!(r#"{{"id": {:?}, "action": {:?}, "proved": {}}}"#, format!("never-errors:{name}"), action, ok));
        }
    }

    for prop in properties() {
        let env = schema.request_envs().find(|e| e.action().to_string() == format!(r#"Action::"{}""#, prop.action)).unwrap();
        let mine = CompiledPolicySet::compile(&memgate, &env, &schema).unwrap();
        let cex = match prop.check {
            Check::NotAlwaysDenies => {
                let denies = symcc.check_always_denies_opt(&mine).await.unwrap();
                if denies { Some("every request is denied".to_string()) } else { None }
            }
            _ => {
                let spec = CompiledPolicySet::compile(&PolicySet::from_str(prop.policy).unwrap(), &env, &schema).unwrap();
                let found = match prop.check {
                    Check::Implies => symcc.check_implies_with_counterexample_opt(&mine, &spec).await.unwrap(),
                    _ => symcc.check_equivalent_with_counterexample_opt(&mine, &spec).await.unwrap(),
                };
                found.map(|e| format!("request {:?}; entities {}", e.request, e.entities.to_json_value().unwrap()))
            }
        };
        let ok = cex.is_none();
        if prop.assumes.is_none() {
            all_ok &= ok;
        }
        println!("{:36} {}{}", prop.id, if ok { "PROVED" } else { "COUNTEREXAMPLE" },
                 prop.assumes.map(|a| format!("   (depends on: {a})")).unwrap_or_default());
        if let Some(c) = &cex {
            println!("    {}", &c[..c.len().min(900)]);
        }
        results.push(format!(
            r#"{{"id": {:?}, "action": {:?}, "claim": {:?}, "proved": {}, "assumes": {}, "counterexample": {}}}"#,
            prop.id, prop.action, prop.claim, ok,
            prop.assumes.map(|a| format!("{a:?}")).unwrap_or("null".into()),
            cex.map(|c| format!("{c:?}")).unwrap_or("null".into())));
    }
    std::fs::write("results.json", format!("[\n {}\n]\n", results.join(",\n "))).unwrap();
    println!("{}", if all_ok { "all unconditional properties proved" } else { "SOME PROPERTIES FAILED" });
    std::process::exit(if all_ok { 0 } else { 1 });
}
