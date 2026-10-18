import {cleanText} from "./rich_text.mjs";

/** Convert human lane numbers to zero-based membership without accepting partial ranges. */
export function parseLaneSelection(text, count) {
  const value = String(text ?? "").trim();
  if (!value) return {lanes: [], error: ""};
  const lanes = new Set();
  for (const part of value.split(",")) {
    const match = part.trim().match(/^(\d+)(?:\s*[-–—]\s*(\d+))?$/);
    if (!match) return {lanes: [], error: "Use lane numbers or ranges, such as 2-5, 8."};
    const first = Number(match[1]), last = Number(match[2] ?? match[1]);
    if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 1 || last > count)
      return {lanes: [], error: `Use lane numbers from 1 to ${count}.`};
    if (last < first) return {lanes: [], error: "Write ranges from low to high, such as 2-5."};
    for (let lane = first; lane <= last; lane++) lanes.add(lane - 1);
  }
  return {lanes: [...lanes].sort((a, b) => a - b), error: ""};
}

/** Keep sparse memberships legible; a range never includes an unselected lane. */
export function formatLaneSelection(lanes) {
  const sorted = [...new Set(lanes)].sort((a, b) => a - b);
  const ranges = [];
  for (let index = 0; index < sorted.length; index++) {
    const first = sorted[index];
    let last = first;
    while (sorted[index + 1] === last + 1) last = sorted[++index];
    ranges.push(first === last ? String(first + 1) : `${first + 1}-${last + 1}`);
  }
  return ranges.join(", ");
}

export function createGroupEditor({getState, isDisabled, onChange, onSelect, onRename, status, onLayout}) {
  const byId = id => document.getElementById(id);
  let selectedGroupId = "", groupSet = 0;
  let draft = {label: "", lanes: ""};
  // Incomplete text stays editable without ever saving an empty/invalid group.
  const membershipEdits = new Map();
  const currentGroup = () => getState()?.annotations.groups.find(group => group.id === selectedGroupId);
  const setValue = (node, value) => { if (node.value !== String(value)) node.value = String(value); };
  const membershipKey = group => group.lanes.join(",");

  function groupText(group) {
    const edit = membershipEdits.get(group.id);
    if (edit && edit.source !== membershipKey(group)) membershipEdits.delete(group.id);
    return membershipEdits.get(group.id)?.text ?? formatLaneSelection(group.lanes);
  }

  function selection() {
    const state = getState(), group = currentGroup();
    return parseLaneSelection(group ? groupText(group) : draft.lanes, state.lanes.length);
  }

  function render() {
    const state = getState();
    if (!state) return;
    const groups = state.annotations.groups.filter(group => group.set === groupSet);
    if (!groups.some(group => group.id === selectedGroupId)) selectedGroupId = "";
    const select = byId("group-select");
    const choices = [{id: "", label: "New group"}, ...groups];
    while (select.options.length > choices.length) select.remove(select.options.length - 1);
    choices.forEach((group, index) => {
      const option = select.options[index] || select.appendChild(document.createElement("option"));
      option.value = group.id;
      option.textContent = group.label || "Untitled group";
    });
    setValue(select, selectedGroupId);
    setValue(byId("group-set"), groupSet);
    const group = currentGroup();
    setValue(byId("group-text"), group?.label ?? draft.label);
    setValue(byId("group-lanes"), group ? groupText(group) : draft.lanes);
    const parsed = selection();
    const error = parsed.error || (group && !parsed.lanes.length ? "Choose at least one lane. The saved group is unchanged." : "");
    byId("group-lanes").setAttribute("aria-invalid", String(Boolean(error)));
    byId("group-error").textContent = error;
    byId("group-error").hidden = !error;
    byId("group-selection-count").textContent = parsed.error ? "Check lane numbers"
      : `${parsed.lanes.length} lane${parsed.lanes.length === 1 ? "" : "s"} selected`;
    byId("group-members").querySelectorAll("input").forEach(node => {
      node.checked = parsed.lanes.includes(Number(node.value));
      node.disabled = isDisabled();
    });
    byId("group-count").textContent = `(${state.annotations.groups.length})`;
    byId("add-group").hidden = Boolean(group);
    byId("new-group").hidden = !group;
    byId("delete-group").hidden = !group;
    byId("add-group").disabled = isDisabled() || !draft.label.trim() || Boolean(parsed.error)
      || !parsed.lanes.length || state.annotations.groups.length >= 100;
    for (const id of ["group-text", "group-lanes", "group-set", "group-select", "all-group-lanes", "clear-group-lanes", "new-group", "delete-group"])
      byId(id).disabled = isDisabled();
    byId("group-hint").textContent = state.annotations.groups.length >= 100 && !group
      ? "The 100-group limit is reached. Edit or delete an existing group."
      : group ? "Changes save automatically. Both group columns appear together."
      : "Enter a name and lane numbers, then create your group.";
  }

  function updateMembership(text) {
    if (isDisabled()) return;
    const group = currentGroup();
    if (!group) { draft.lanes = text; render(); return; }
    const parsed = parseLaneSelection(text, getState().lanes.length);
    const different = !parsed.error && parsed.lanes.length && parsed.lanes.join(",") !== membershipKey(group);
    if (different) group.lanes = parsed.lanes;
    membershipEdits.set(group.id, {text, source: membershipKey(group)});
    if (different) onChange();
    else render();
  }

  function buildMembership() {
    const container = byId("group-members");
    container.replaceChildren();
    getState().lanes.forEach((_, index) => {
      const label = document.createElement("label"), checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = String(index);
      checkbox.setAttribute("aria-label", `Include lane ${index + 1}`);
      label.append(checkbox, document.createTextNode(String(index + 1)));
      container.appendChild(label);
      checkbox.addEventListener("change", () => {
        const members = [...container.querySelectorAll("input")].filter(node => node.checked).map(node => Number(node.value));
        updateMembership(formatLaneSelection(members));
      });
    });
  }

  function selectGroup(id) {
    const group = getState()?.annotations.groups.find(group => group.id === id);
    if (!group) return;
    selectedGroupId = id;
    groupSet = group.set;
    render();
  }

  function openNew() {
    if (isDisabled()) return;
    selectedGroupId = "";
    render();
    byId("group-panel").open = true;
    byId("group-text").focus();
    onLayout();
  }

  function openGroup(id) {
    if (isDisabled()) return;
    selectGroup(id);
    if (currentGroup()) onSelect(id);
    byId("group-panel").open = true;
    byId("group-text").focus();
    onLayout();
  }

  function create() {
    const state = getState(), parsed = selection();
    if (isDisabled() || currentGroup() || !draft.label.trim() || parsed.error || !parsed.lanes.length || state.annotations.groups.length >= 100) return;
    const id = `group-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    const label = draft.label;
    state.annotations.groups.push({id, set: groupSet, label, lanes: parsed.lanes,
      bold: false, italic: false, color: "#000000"});
    draft = {label: "", lanes: ""};
    onSelect(id);
    onChange();
    status(`Created “${label}” for lanes ${formatLaneSelection(parsed.lanes)}.`);
    byId("group-text").focus();
    onLayout();
  }

  function validate() {
    const state = getState();
    for (const group of state.annotations.groups) {
      const parsed = parseLaneSelection(groupText(group), state.lanes.length);
      if (!parsed.error && parsed.lanes.length) continue;
      openGroup(group.id);
      byId("group-lanes").focus();
      status("Check the group's lane numbers before confirming annotations.", true);
      return false;
    }
    return true;
  }

  byId("group-panel").addEventListener("toggle", onLayout);
  byId("group-lane-picker").addEventListener("toggle", onLayout);
  byId("group-set").addEventListener("change", event => {
    groupSet = Number(event.target.value);
    selectedGroupId = "";
    render();
  });
  byId("group-select").addEventListener("change", event => {
    selectedGroupId = event.target.value;
    if (selectedGroupId) onSelect(selectedGroupId);
    render();
  });
  byId("group-text").addEventListener("input", event => {
    if (isDisabled()) return;
    const group = currentGroup();
    if (group) onRename(group.id, event.target.value);
    else { draft.label = cleanText(event.target.value); render(); }
  });
  byId("group-lanes").addEventListener("input", event => updateMembership(event.target.value));
  for (const id of ["group-text", "group-lanes"]) byId(id).addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.isComposing && !currentGroup()) { event.preventDefault(); create(); }
  });
  byId("all-group-lanes").addEventListener("click", () =>
    updateMembership(formatLaneSelection(getState().lanes.map((_, index) => index))));
  byId("clear-group-lanes").addEventListener("click", () => updateMembership(""));
  byId("add-group").addEventListener("click", create);
  byId("new-group").addEventListener("click", openNew);
  byId("delete-group").addEventListener("click", () => {
    if (isDisabled() || !currentGroup()) return;
    getState().annotations.groups = getState().annotations.groups.filter(group => group.id !== selectedGroupId);
    membershipEdits.delete(selectedGroupId);
    selectedGroupId = "";
    onChange();
    byId("group-text").focus();
  });

  return {render, selectGroup, openNew, openGroup, validate,
    reset() {
      selectedGroupId = ""; groupSet = 0;
      draft = {label: "", lanes: ""};
      membershipEdits.clear();
      byId("group-panel").open = false;
      byId("group-lane-picker").open = false;
      buildMembership();
      render();
    }};
}
