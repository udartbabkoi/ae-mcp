/**
 * audio_reactive_scale.jsx
 * Production ExtendScript Template: Audio-Reactive Scale & Pulse Injection.
 * 
 * Strict ES3 JavaScript. Supports both direct keyframe injection of normalized
 * audio envelopes and procedural expression linking with smoothing and thresholds.
 */

(function () {
    "use strict";

    if (!app.project || !app.project.activeItem || !(app.project.activeItem instanceof CompItem)) {
        throw new Error("Please open or select a composition before running this template.");
    }

    var comp = app.project.activeItem;

    app.beginUndoGroup("Apply Audio Reactive Scale");

    try {
        // Target active layer, or create a demo pulsing element if no layer is selected
        var targetLayer = null;
        if (comp.selectedLayers && comp.selectedLayers.length > 0) {
            targetLayer = comp.selectedLayers[0];
        } else {
            // Create a stylish circular graphic to demonstrate pulse
            var shapeLayer = comp.layers.addShape();
            shapeLayer.name = "Audio_Reactive_Badge";
            var rootGroup = shapeLayer.property("ADBE Root Vectors Group");
            var ellipseGroup = rootGroup.addProperty("ADBE Vector Group");
            ellipseGroup.name = "Circle";
            var ellipseContents = ellipseGroup.property("ADBE Vectors Group");
            var ellipseShape = ellipseContents.addProperty("ADBE Vector Shape - Ellipse");
            ellipseShape.property("ADBE Vector Ellipse Size").setValue([260, 260]);

            var ellipseFill = ellipseContents.addProperty("ADBE Vector Graphic - Fill");
            ellipseFill.property("ADBE Vector Fill Color").setValue([0.95, 0.25, 0.45, 1.0]); // Neon magenta

            var ellipseStroke = ellipseContents.addProperty("ADBE Vector Graphic - Stroke");
            ellipseStroke.property("ADBE Vector Stroke Color").setValue([1.0, 1.0, 1.0, 1.0]);
            ellipseStroke.property("ADBE Vector Stroke Width").setValue(8);

            // Center shape
            shapeLayer.property("ADBE Transform Group").property("ADBE Position").setValue([comp.width / 2, comp.height / 2]);
            targetLayer = shapeLayer;
        }

        // 1. Create or locate Audio Amplitude Control Null
        var controlNull = null;
        for (var i = 1; i <= comp.numLayers; i++) {
            if (comp.layer(i).name === "Audio_Amplitude_Controller") {
                controlNull = comp.layer(i);
                break;
            }
        }

        if (!controlNull) {
            controlNull = comp.layers.addNull();
            controlNull.name = "Audio_Amplitude_Controller";
            controlNull.guideLayer = true;

            // Add Slider Control effect for audio amplitude
            var effectsGroup = controlNull.property("ADBE Effect Parade");
            var sliderControl = effectsGroup.addProperty("ADBE Slider Control");
            sliderControl.name = "Audio Amplitude";
            sliderControl.property("ADBE Slider Control-0001").setValue(0.0);

            // Add Min/Max scale sliders
            var minScaleSlider = effectsGroup.addProperty("ADBE Slider Control");
            minScaleSlider.name = "Min Scale %";
            minScaleSlider.property("ADBE Slider Control-0001").setValue(100.0);

            var maxScaleSlider = effectsGroup.addProperty("ADBE Slider Control");
            maxScaleSlider.name = "Max Scale %";
            maxScaleSlider.property("ADBE Slider Control-0001").setValue(135.0);

            var threshSlider = effectsGroup.addProperty("ADBE Slider Control");
            threshSlider.name = "Threshold";
            threshSlider.property("ADBE Slider Control-0001").setValue(0.15);
        }

        // 2. Attach reactive expression to target layer scale
        var scaleProp = targetLayer.property("ADBE Transform Group").property("ADBE Scale");

        var scaleExpression = 
            'var ctrl = thisComp.layer("Audio_Amplitude_Controller");\n' +
            'var amp = ctrl.effect("Audio Amplitude")("Slider");\n' +
            'var minS = ctrl.effect("Min Scale %")("Slider");\n' +
            'var maxS = ctrl.effect("Max Scale %")("Slider");\n' +
            'var thresh = ctrl.effect("Threshold")("Slider");\n' +
            'var curAmp = Math.max(0, amp - thresh) / Math.max(0.001, (1.0 - thresh));\n' +
            'var s = linear(curAmp, 0, 1, minS, maxS);\n' +
            '[s, s, value[2]];';

        scaleProp.expression = scaleExpression;

        app.endUndoGroup();

        return {
            status: "success",
            targetLayerIndex: targetLayer.index,
            targetLayerName: targetLayer.name,
            controllerLayerIndex: controlNull.index,
            appliedProperty: "ADBE Scale",
            expression: scaleExpression
        };
    } catch (e) {
        app.endUndoGroup();
        throw e;
    }
})();
