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

// Carrying a memory into personal memory drops its location and participant labels, so it needs
// the reader's own access to it and the permission of every environment it was formed in.
@id("carry-out-if-environments-allow")
permit (principal, action == Action::"writePersonal", resource)
when {
  [principal].containsAll(resource.selfs) &&
  (resource.withs.isEmpty() || resource.withs.contains(principal)) &&
  resource.carryTypes.contains(context.memoryType)
};

@id("never-carry-out-of-high-assurance")
forbid (principal, action == Action::"writePersonal", resource)
when { !resource.haLocs.isEmpty() };
