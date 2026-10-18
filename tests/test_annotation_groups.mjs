import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createGroupEditor, formatLaneSelection, parseLaneSelection} from "../gel_analyzer/annotation_component_frontend/groups.mjs";
import {editText, formatRange} from "../gel_analyzer/annotation_component_frontend/rich_text.mjs";

test("lane ranges accept mixed sparse membership, normalize duplicates, and preserve one-based numbering", () => {
  assert.deepEqual(parseLaneSelection(" 2 - 5, 8, 3, 10–11, 14—15 ", 16),
    {lanes: [1, 2, 3, 4, 7, 9, 10, 13, 14], error: ""});
  assert.deepEqual(parseLaneSelection("", 16), {lanes: [], error: ""});
  const lanes = [7, 1, 2, 3, 4, 9, 10, 13, 14, 1];
  assert.equal(formatLaneSelection(lanes), "2-5, 8, 10-11, 14-15");
  assert.deepEqual(parseLaneSelection(formatLaneSelection(lanes), 16).lanes, [1, 2, 3, 4, 7, 9, 10, 13, 14]);
});

test("invalid or unfinished lane input never produces partial membership", () => {
  for (const text of ["2-", "2,", "1,,3", "2 3", "one", "1.5", "-1", "0", "1-9", "8-2", "99999999999999999999999"]) {
    const parsed = parseLaneSelection(text, 8);
    assert.notEqual(parsed.error, "", text);
    assert.deepEqual(parsed.lanes, [], text);
  }
  assert.match(parseLaneSelection("8-2", 8).error, /low to high/);
  assert.match(parseLaneSelection("0", 8).error, /1 to 8/);
});

class Node {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.attributes = {};
    this.events = {};
    this.value = "";
    this.textContent = "";
    this.disabled = false;
    this.hidden = false;
    this.checked = false;
    this.open = false;
  }
  get options() { return this.children; }
  remove(index) { this.children.splice(index, 1); }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  querySelectorAll(tag) {
    return this.children.flatMap(child => [...(child.tagName === tag ? [child] : []), ...child.querySelectorAll(tag)]);
  }
  focus() { globalThis.document.activeElement = this; }
  addEventListener(name, callback) { (this.events[name] ??= []).push(callback); }
  dispatch(name, values = {}) {
    if (this.disabled) return;
    const event = {target: this, ...values, preventDefault() { this.prevented = true; }};
    for (const callback of this.events[name] ?? []) callback(event);
    return event;
  }
}

function harness(run, groups = []) {
  const previousDocument = globalThis.document;
  const html = readFileSync(new URL("../gel_analyzer/annotation_component_frontend/index.html", import.meta.url), "utf8");
  const nodes = Object.fromEntries([...html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)]
    .map(match => [match[2], new Node(match[1])]));
  globalThis.document = {getElementById: id => nodes[id], createElement: tag => new Node(tag),
    createTextNode: text => Object.assign(new Node("#text"), {textContent: text})};
  const state = {lanes: Array.from({length: 12}, (_, index) => [0, 10 * index, 100, 10 * index + 8]),
    annotations: {groups: structuredClone(groups)}};
  const selected = [], messages = [], edits = [];
  let disabled = false;
  const controller = createGroupEditor({getState: () => state, isDisabled: () => disabled,
    onChange() { edits.push(structuredClone(state)); controller.render(); },
    onSelect(id) { selected.push(id); },
    onRename(id, text) {
      editText(state.annotations.groups.find(group => group.id === id), "label", text);
      edits.push(structuredClone(state)); controller.render();
    }, status(...message) { messages.push(message); }, onLayout() {}});
  const input = (id, value) => { nodes[id].value = value; nodes[id].dispatch("input"); };
  const select = (id, value) => { nodes[id].value = value; nodes[id].dispatch("change"); };
  const click = id => nodes[id].dispatch("click");
  const checkbox = index => nodes["group-members"].querySelectorAll("input")[index];
  try {
    controller.reset();
    run({state, nodes, controller, input, select, click, checkbox, selected, messages, edits,
      setDisabled(value) { disabled = value; controller.render(); }});
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
}

const group = (id = "existing", set = 0) => ({id, set, label: "Control treated", lanes: [1, 2, 5],
  bold: false, italic: false, color: "#000000"});

test("new groups start empty and range entry creates sparse membership without selecting lane 1", () => harness(h => {
  h.controller.openNew();
  assert.equal(h.nodes["group-panel"].open, true);
  assert.equal(h.nodes["group-lanes"].value, "");
  assert.equal(h.checkbox(0).checked, false);
  assert.equal(h.nodes["add-group"].disabled, true);
  h.input("group-text", "Treatment");
  h.input("group-lanes", "2-5, 8");
  assert.equal(h.nodes["group-selection-count"].textContent, "5 lanes selected");
  assert.equal(h.nodes["add-group"].disabled, false);
  h.click("add-group");
  const created = h.state.annotations.groups[0];
  assert.equal(created.label, "Treatment");
  assert.deepEqual(created.lanes, [1, 2, 3, 4, 7]);
  assert.deepEqual(h.selected, [created.id]);
  assert.match(h.messages.at(-1)[0], /Created “Treatment”/);
  assert.equal(h.nodes["group-panel"].open, true, "the form stays available for another group");
  assert.equal(h.nodes["group-text"].value, "");
  assert.equal(h.nodes["group-lanes"].value, "");
  assert.equal(document.activeElement, h.nodes["group-text"]);
  assert.equal(h.nodes["add-group"].disabled, true);
}));

test("unfinished range and label drafts survive opening or switching groups, and Enter only creates valid groups", () => harness(h => {
  h.controller.openNew();
  h.input("group-text", "Draft");
  h.input("group-lanes", "2-");
  h.nodes["group-lanes"].dispatch("keydown", {key: "Enter"});
  assert.equal(h.state.annotations.groups.length, 1);
  h.select("group-select", "existing");
  assert.equal(h.nodes["group-text"].value, "Control treated");
  h.controller.openNew();
  assert.equal(h.nodes["group-text"].value, "Draft");
  assert.equal(h.nodes["group-lanes"].value, "2-");
  assert.equal(h.nodes["group-lanes"].attributes["aria-invalid"], "true");
  h.input("group-lanes", "2-4");
  h.select("group-set", "1");
  assert.equal(h.nodes["group-text"].value, "Draft");
  h.nodes["group-lanes"].dispatch("keydown", {key: "Enter", isComposing: true});
  assert.equal(h.state.annotations.groups.length, 1, "IME confirmation does not create a group");
  const event = h.nodes["group-lanes"].dispatch("keydown", {key: "Enter"});
  assert.equal(event.prevented, true);
  assert.equal(h.state.annotations.groups.length, 2);
  assert.equal(h.state.annotations.groups[1].set, 1);
  assert.deepEqual(h.state.annotations.groups[1].lanes, [1, 2, 3]);
}, [group()]));

test("All lanes, Clear, and individual checkboxes share one membership field", () => harness(h => {
  h.controller.openNew();
  h.input("group-text", "All");
  h.click("all-group-lanes");
  assert.equal(h.nodes["group-lanes"].value, "1-12");
  assert.equal(h.nodes["group-selection-count"].textContent, "12 lanes selected");
  h.click("clear-group-lanes");
  assert.equal(h.nodes["group-lanes"].value, "");
  assert.equal(h.nodes["add-group"].disabled, true);
  for (const index of [3, 4, 7]) { h.checkbox(index).checked = true; h.checkbox(index).dispatch("change"); }
  assert.equal(h.nodes["group-lanes"].value, "4-5, 8");
  h.click("add-group");
  assert.deepEqual(h.state.annotations.groups[0].lanes, [3, 4, 7]);
}));

test("existing groups can be renamed without dropping rich-text styles or changing sparse membership", () => {
  const value = group();
  formatRange(value, "label", 8, 15, {bold: true, color: "#ff0000"});
  harness(h => {
    h.controller.openGroup("existing");
    assert.equal(h.nodes["group-text"].value, "Control treated");
    assert.equal(h.nodes["group-lanes"].value, "2-3, 6");
    assert.equal(h.nodes["add-group"].hidden, true);
    assert.equal(h.nodes["new-group"].hidden, false);
    h.input("group-text", "Control treated sample");
    const saved = h.state.annotations.groups[0];
    assert.equal(saved.label, "Control treated sample");
    assert.equal(saved.runs[0].color, "#000000");
    assert.equal(saved.runs[1].text, "treated sample");
    assert.equal(saved.runs[1].color, "#ff0000");
    assert.equal(saved.runs[1].bold, true);
    assert.deepEqual(saved.lanes, [1, 2, 5]);
    h.input("group-lanes", "3-4, 9");
    assert.deepEqual(saved.lanes, [2, 3, 8]);
    assert.equal(saved.runs[1].bold, true);
    assert.equal(h.controller.validate(), true);
  }, [value]);
});

test("incomplete or empty saved-group membership stays visible, preserves saved lanes, and blocks confirmation", () => harness(h => {
  h.controller.openGroup("existing");
  h.input("group-lanes", "2-");
  assert.deepEqual(h.state.annotations.groups[0].lanes, [1, 2, 5]);
  h.controller.render();
  assert.equal(h.nodes["group-lanes"].value, "2-");
  h.controller.openNew();
  assert.equal(h.controller.validate(), false);
  assert.equal(h.nodes["group-select"].value, "existing");
  assert.equal(document.activeElement, h.nodes["group-lanes"]);
  h.click("clear-group-lanes");
  assert.equal(h.nodes["group-selection-count"].textContent, "0 lanes selected");
  assert.deepEqual(h.state.annotations.groups[0].lanes, [1, 2, 5]);
  assert.equal(h.controller.validate(), false);
  h.input("group-lanes", "5-7");
  assert.deepEqual(h.state.annotations.groups[0].lanes, [4, 5, 6]);
  assert.equal(h.controller.validate(), true);
  assert.equal(h.nodes["group-error"].hidden, true);
}, [group()]));

test("confirmation ignores uncreated drafts and a new gel resets all drafts and selection", () => harness(h => {
  h.controller.openNew();
  h.input("group-text", "Not created");
  h.input("group-lanes", "2-");
  assert.equal(h.controller.validate(), true);
  h.controller.reset();
  assert.equal(h.nodes["group-text"].value, "");
  assert.equal(h.nodes["group-lanes"].value, "");
  assert.equal(h.nodes["group-panel"].open, false);
  assert.equal(h.checkbox(0).checked, false);
}));

test("saved groups in both columns remain individually editable and removable", () => harness(h => {
  h.controller.selectGroup("far");
  assert.equal(h.nodes["group-set"].value, "1");
  assert.equal(h.nodes["group-select"].value, "far");
  h.click("delete-group");
  assert.deepEqual(h.state.annotations.groups.map(value => value.id), ["near"]);
  assert.equal(h.nodes["group-select"].value, "");
  assert.equal(h.nodes["group-lanes"].value, "");
  h.controller.selectGroup("near");
  h.click("new-group");
  assert.equal(h.nodes["group-set"].value, "0");
  assert.equal(h.nodes["group-select"].value, "");
  assert.equal(h.nodes["group-lanes"].value, "");
}, [group("near"), group("far", 1)]));

test("composing confirmation locks membership and group creation without erasing drafts", () => harness(h => {
  h.controller.openNew();
  h.input("group-text", "Draft");
  h.input("group-lanes", "2-4");
  h.setDisabled(true);
  h.click("add-group");
  h.click("clear-group-lanes");
  assert.equal(h.state.annotations.groups.length, 0);
  assert.equal(h.nodes["group-lanes"].value, "2-4");
  assert.equal(h.checkbox(1).disabled, true);
  h.setDisabled(false);
  h.click("add-group");
  assert.deepEqual(h.state.annotations.groups[0].lanes, [1, 2, 3]);
}));

test("the saved-group limit disables both click and keyboard creation without dropping a draft", () => harness(h => {
  h.controller.openNew();
  h.input("group-text", "Draft");
  h.input("group-lanes", "2-4");
  assert.equal(h.nodes["add-group"].disabled, true);
  h.nodes["group-lanes"].dispatch("keydown", {key: "Enter"});
  assert.equal(h.state.annotations.groups.length, 100);
  assert.equal(h.nodes["group-text"].value, "Draft");
  assert.match(h.nodes["group-hint"].textContent, /100-group limit/);
}, Array.from({length: 100}, (_, index) => group(`g-${index}`))));
