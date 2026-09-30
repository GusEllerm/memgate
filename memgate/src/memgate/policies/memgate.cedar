// Recall: every identity and location label must be held, and the reader must be a participant.
@id("read-labels")
permit (principal, action == Action::"read", resource)
when {
  [principal].containsAll(resource.selfs) &&
  [context.location].containsAll(resource.locs) &&
  (resource.withs.isEmpty() || resource.withs.contains(principal))
};

// High assurance is outbound only: nothing formed in a high-assurance location is recalled outside it.
@id("high-assurance-seal")
forbid (principal, action == Action::"read", resource)
unless { [context.location].containsAll(resource.haLocs) };

// Writing: the writer holds every identity label (never another agent's), and either there is one
// (personal memory, notes) or the writer is a participant (conversations). A label set with a
// location may only be written in that location.
@id("write-labels")
permit (principal, action == Action::"write", resource)
when {
  [principal].containsAll(resource.selfs) &&
  (!resource.selfs.isEmpty() || resource.withs.contains(principal)) &&
  [context.location].containsAll(resource.locs)
};

// High assurance is outbound only, for writes too: anything written in a high-assurance location
// carries that location's label, so it can never be recalled outside it.
@id("high-assurance-write-seal")
forbid (principal, action == Action::"write", resource)
when { context.location.highAssurance && !resource.locs.contains(context.location) };

// Carrying a memory into personal memory drops its location and participant labels, so it needs
// the carrier's own access to it where it is (the source must be readable here) and the permission
// of every environment it was formed in.
@id("carry-out-if-environments-allow")
permit (principal, action == Action::"writePersonal", resource)
when {
  [principal].containsAll(resource.selfs) &&
  (resource.withs.isEmpty() || resource.withs.contains(principal)) &&
  [context.location].containsAll(resource.locs) &&
  resource.carryTypes.contains(context.memoryType)
};

@id("never-carry-out-of-high-assurance")
forbid (principal, action == Action::"writePersonal", resource)
when { !resource.haLocs.isEmpty() };
