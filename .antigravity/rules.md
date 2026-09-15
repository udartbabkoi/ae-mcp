# Adobe After Effects ExtendScript Agent Rules & Architecture Guidelines

When generating, modifying, or executing ExtendScript for Adobe After Effects via `ae-mcp`, agents MUST strictly adhere to the following rules, constraints, and conventions.

---

## 1. Strict ES3 JavaScript Syntax (Zero-Tolerance)

After Effects' ExtendScript virtual machine is based on **ECMAScript 3 (1999)**. Any modern JavaScript syntax will cause an immediate compilation crash (`SyntaxError`).

### Prohibited Syntax:
- ❌ **NO `let` or `const`**: Use `var` exclusively.
- ❌ **NO Arrow Functions (`() => {}`)**: Use `function name() {}` or anonymous `function () {}`.
- ❌ **NO Template Literals (`` `Hello ${name}` ``)**: Use standard string concatenation (`"Hello " + name`).
- ❌ **NO Default Parameters (`function foo(x = 1)`)**: Initialize manually inside the body (`if (x === undefined) x = 1;`).
- ❌ **NO Destructuring (`var { a, b } = obj`)**: Access properties directly (`var a = obj.a;`).
- ❌ **NO Spread/Rest Operator (`...args`)**: Use `arguments` or explicit iteration.
- ❌ **NO Modern Array Methods**: `Array.prototype.find`, `includes`, `findIndex`, `flat`, `forEach`, `map` are **not available** natively. Use standard `for (var i = 0; i < arr.length; i++)`.
- ❌ **NO `for...of`**: Use index-based `for` loops or `for (var key in obj)` with `hasOwnProperty` checks.
- ❌ **NO Native `JSON` Object**: ExtendScript does not have a global `JSON` object unless polyfilled. `ae-mcp` automatically bundles `json2.jsx`, but standalone scripts must include or account for this.

---

## 2. Language-Invariant Match Names

Adobe After Effects is localized into more than 10 languages (German, French, Japanese, Spanish, Chinese, etc.).
Using display names like `layer.property("Position")` or `layer("Transform")` **WILL FAIL** on non-English installations.
**Always reference properties using language-invariant match names.**

### Essential Match Names Reference:

| Transform Properties | Match Name |
| :--- | :--- |
| Transform Group | `ADBE Transform Group` |
| Position | `ADBE Position` |
| Scale | `ADBE Scale` |
| Rotation (2D) | `ADBE Rotate Z` |
| Rotation (3D X/Y/Z) | `ADBE Rotate X`, `ADBE Rotate Y`, `ADBE Rotate Z` |
| Opacity | `ADBE Opacity` |
| Anchor Point | `ADBE Anchor Point` |

| Mask Properties | Match Name |
| :--- | :--- |
| Masks Root | `ADBE Mask Parade` |
| Individual Mask Element | `ADBE Mask Atom` |
| Mask Path / Shape | `ADBE Mask Shape` |
| Mask Feather | `ADBE Mask Feather` |
| Mask Opacity | `ADBE Mask Opacity` |
| Mask Expansion | `ADBE Mask Offset` |

| Shape Layer Hierarchy | Match Name |
| :--- | :--- |
| Root Vector Container | `ADBE Root Vectors Group` |
| Shape Group | `ADBE Vector Group` |
| Group Contents Container | `ADBE Vectors Group` |
| Rectangle Path | `ADBE Vector Shape - Rect` |
| Ellipse Path | `ADBE Vector Shape - Ellipse` |
| Solid Fill | `ADBE Vector Graphic - Fill` |
| Stroke | `ADBE Vector Graphic - Stroke` |
| Trim Paths | `ADBE Vector Filter - Trim` |

| Text Properties | Match Name |
| :--- | :--- |
| Text Root | `ADBE Text Properties` |
| Text Document (Font, Size, Color) | `ADBE Text Document` |

---

## 3. Coordinate Spaces & Geometric Math

After Effects has three distinct coordinate spaces:
1. **Composition Space**: Canvas coordinate system from `[0, 0]` (top-left) to `[comp.width, comp.height]`.
2. **Layer Space**: Local layer coordinate system from `[0, 0]` (top-left of footage/solid) to `[layer.width, layer.height]`.
3. **Shape Group Space**: Local origin defined by the vector group's anchor point.

### Guidelines for Coordinate Calculations:
- **Mask Vertices**: Mask coordinates are in **Layer Space**.
  - A vertex at the layer center is `[layer.width / 2, layer.height / 2]`.
  - Never place mask vertices using composition coordinates unless converted via layer transform offsets.
- **Dynamic Sizing (`sourceRectAtTime`)**:
  - Always pass `time` and `false` (ignore extents) when measuring text: `layer.sourceRectAtTime(time, false)`.
  - Account for top/left offsets: text boxes often have non-zero `rect.top` and `rect.left` due to font ascenders/descenders.

---

## 4. Undo Group Discipline

Every operation modifying the project or composition must be safely wrapped in an undo group. Unbalanced undo groups break user undo history and corrupt the internal state.

```javascript
app.beginUndoGroup("Descriptive Action Name");
try {
    // Perform composition changes here
} catch (err) {
    // Cleanly catch and re-throw or report
    throw err;
} finally {
    app.endUndoGroup();
}
```

---

## 5. Track Matte Compatibility (Dual-Engine)

After Effects 2023 (v23.0+) introduced arbitrary layer track mattes, deprecating the legacy requirement that a matte layer must reside directly above the target layer.
Always write dual-compatible code:

```javascript
function linkAlphaTrackMatte(targetLayer, matteLayer) {
    if (typeof targetLayer.setTrackMatte === "function") {
        // Modern AE 2023+ (v23.0+)
        targetLayer.setTrackMatte(matteLayer, TrackMatteType.ALPHA);
    } else {
        // Legacy AE fallback
        matteLayer.moveBefore(targetLayer);
        targetLayer.trackMatteType = TrackMatteType.ALPHA;
    }
}
```

---

## 6. Defensive Project & Layer Validation

Always validate project and active item states before performing modifications:

```javascript
if (!app.project) {
    throw new Error("No project is open in After Effects.");
}
var comp = app.project.activeItem;
if (!comp || !(comp instanceof CompItem)) {
    throw new Error("No active composition open in the viewer.");
}
if (layerIndex < 1 || layerIndex > comp.numLayers) {
    throw new Error("Layer index " + layerIndex + " is out of bounds (1 to " + comp.numLayers + ").");
}
```
