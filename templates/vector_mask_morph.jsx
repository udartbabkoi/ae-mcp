/**
 * vector_mask_morph.jsx
 * Production ExtendScript Template: Vector Mask Shape Keyframe Morphing.
 * 
 * Strict ES3 JavaScript. Demonstrates interpolating ADBE Mask Shape vertices
 * over time between distinct geometric polygons (Square -> Diamond -> Star).
 */

(function () {
    "use strict";

    if (!app.project || !app.project.activeItem || !(app.project.activeItem instanceof CompItem)) {
        throw new Error("Please open or select a composition before running this template.");
    }

    var comp = app.project.activeItem;

    app.beginUndoGroup("Create Vector Mask Morph");

    try {
        var targetLayer = null;

        if (comp.selectedLayers && comp.selectedLayers.length > 0) {
            targetLayer = comp.selectedLayers[0];
        } else {
            // Create a rich gradient solid to showcase the mask morphing
            var solidColor = [0.15, 0.45, 0.95];
            targetLayer = comp.layers.addSolid(solidColor, "Morphing_Mask_Layer", comp.width, comp.height, comp.pixelAspect, comp.duration);
        }

        var maskParade = targetLayer.property("ADBE Mask Parade");
        if (!maskParade) {
            throw new Error("Target layer does not support mask operations.");
        }

        var mask = maskParade.addProperty("ADBE Mask Atom");
        mask.name = "Vector Morph Mask";
        mask.maskMode = MaskMode.ADD;

        var maskShapeProp = mask.property("ADBE Mask Shape");

        // Center coordinates relative to layer
        var cx = targetLayer.width / 2;
        var cy = targetLayer.height / 2;
        var r = Math.min(targetLayer.width, targetLayer.height) * 0.22;

        // Shape 1: Octagon / Rounded Square (8 vertices)
        // [cx + dx, cy + dy]
        var shape1 = new Shape();
        var s1Verts = [
            [cx - r * 0.5, cy - r],
            [cx + r * 0.5, cy - r],
            [cx + r, cy - r * 0.5],
            [cx + r, cy + r * 0.5],
            [cx + r * 0.5, cy + r],
            [cx - r * 0.5, cy + r],
            [cx - r, cy + r * 0.5],
            [cx - r, cy - r * 0.5]
        ];
        shape1.vertices = s1Verts;
        shape1.inTangents = [
            [-r * 0.15, 0], [r * 0.15, 0],
            [0, -r * 0.15], [0, r * 0.15],
            [r * 0.15, 0], [-r * 0.15, 0],
            [0, r * 0.15], [0, -r * 0.15]
        ];
        shape1.outTangents = [
            [r * 0.15, 0], [-r * 0.15, 0],
            [0, r * 0.15], [0, -r * 0.15],
            [-r * 0.15, 0], [r * 0.15, 0],
            [0, -r * 0.15], [0, r * 0.15]
        ];
        shape1.closed = true;

        // Shape 2: 4-Point Star (8 vertices matching topology)
        var shape2 = new Shape();
        var rInner = r * 0.35;
        var rOuter = r * 1.35;
        var s2Verts = [
            [cx, cy - rOuter],                         // Top point
            [cx + rInner * 0.7, cy - rInner * 0.7],    // Top-Right valley
            [cx + rOuter, cy],                         // Right point
            [cx + rInner * 0.7, cy + rInner * 0.7],    // Bottom-Right valley
            [cx, cy + rOuter],                         // Bottom point
            [cx - rInner * 0.7, cy + rInner * 0.7],    // Bottom-Left valley
            [cx - rOuter, cy],                         // Left point
            [cx - rInner * 0.7, cy - rInner * 0.7]     // Top-Left valley
        ];
        shape2.vertices = s2Verts;
        shape2.inTangents = [
            [0, 0], [0, 0], [0, 0], [0, 0],
            [0, 0], [0, 0], [0, 0], [0, 0]
        ];
        shape2.outTangents = [
            [0, 0], [0, 0], [0, 0], [0, 0],
            [0, 0], [0, 0], [0, 0], [0, 0]
        ];
        shape2.closed = true;

        // Shape 3: Diamond Shield (8 vertices matching topology)
        var shape3 = new Shape();
        var s3Verts = [
            [cx, cy - r * 1.1],
            [cx + r * 0.6, cy - r * 0.5],
            [cx + r * 0.9, cy + 0],
            [cx + r * 0.5, cy + r * 0.7],
            [cx, cy + r * 1.25],
            [cx - r * 0.5, cy + r * 0.7],
            [cx - r * 0.9, cy + 0],
            [cx - r * 0.6, cy - r * 0.5]
        ];
        shape3.vertices = s3Verts;
        shape3.inTangents = [
            [-r * 0.2, 0], [0, -r * 0.1],
            [0, -r * 0.1], [0, -r * 0.1],
            [r * 0.1, 0], [-r * 0.1, 0],
            [0, r * 0.1], [0, r * 0.1]
        ];
        shape3.outTangents = [
            [r * 0.2, 0], [0, r * 0.1],
            [0, r * 0.1], [0, r * 0.1],
            [-r * 0.1, 0], [r * 0.1, 0],
            [0, -r * 0.1], [0, -r * 0.1]
        ];
        shape3.closed = true;

        // Set keyframes on ADBE Mask Shape across timeline
        var t0 = comp.workAreaStart;
        maskShapeProp.setValueAtTime(t0, shape1);
        maskShapeProp.setValueAtTime(t0 + 1.0, shape2);
        maskShapeProp.setValueAtTime(t0 + 2.0, shape3);
        maskShapeProp.setValueAtTime(t0 + 3.0, shape1);

        // Apply smooth temporal easing to mask keyframes
        var easeIn = new KeyframeEase(0, 65);
        var easeOut = new KeyframeEase(0, 65);
        for (var k = 1; k <= maskShapeProp.numKeys; k++) {
            maskShapeProp.setTemporalEaseAtKey(k, [easeIn], [easeOut]);
        }

        // Add slight mask feather for smooth rendering
        var featherProp = mask.property("ADBE Mask Feather");
        if (featherProp) {
            featherProp.setValue([4, 4]);
        }

        app.endUndoGroup();

        return {
            status: "success",
            layerIndex: targetLayer.index,
            layerName: targetLayer.name,
            maskIndex: mask.propertyIndex,
            keyframesCount: maskShapeProp.numKeys,
            timelineRange: [t0, t0 + 3.0]
        };
    } catch (e) {
        app.endUndoGroup();
        throw e;
    }
})();
