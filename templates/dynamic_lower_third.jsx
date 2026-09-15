/**
 * dynamic_lower_third.jsx
 * Production ExtendScript Template: Dynamic Lower Third with Auto-Sizing Background.
 * 
 * Strict ES3 JavaScript. Uses sourceRectAtTime expressions so the background
 * rectangle automatically recalculates width, height, and position whenever
 * text changes.
 */

(function () {
    "use strict";

    if (!app.project || !app.project.activeItem || !(app.project.activeItem instanceof CompItem)) {
        throw new Error("Please open or select a composition before running this template.");
    }

    var comp = app.project.activeItem;

    app.beginUndoGroup("Create Dynamic Lower Third");

    try {
        var compWidth = comp.width;
        var compHeight = comp.height;
        var fps = comp.frameRate;

        // Position coordinates in lower-left third
        var marginX = compWidth * 0.08;
        var marginY = compHeight * 0.82;

        // 1. Title Text Layer
        var titleLayer = comp.layers.addText("ALEXANDER RIVERA");
        titleLayer.name = "LT_Title";
        var titleTextProp = titleLayer.property("ADBE Text Properties").property("ADBE Text Document");
        var titleDoc = titleTextProp.value;
        titleDoc.fontSize = Math.round(compHeight * 0.042);
        titleDoc.fillColor = [1.0, 1.0, 1.0];
        titleDoc.applyFill = true;
        titleDoc.font = "Arial-BoldMT";
        titleDoc.justification = ParagraphJustification.LEFT_JUSTIFY;
        titleTextProp.setValue(titleDoc);

        var titlePos = titleLayer.property("ADBE Transform Group").property("ADBE Position");
        titlePos.setValue([marginX + 30, marginY - 15]);

        // 2. Subtitle Text Layer
        var subLayer = comp.layers.addText("CHIEF SYSTEMS ARCHITECT");
        subLayer.name = "LT_Subtitle";
        var subTextProp = subLayer.property("ADBE Text Properties").property("ADBE Text Document");
        var subDoc = subTextProp.value;
        subDoc.fontSize = Math.round(compHeight * 0.022);
        subDoc.fillColor = [0.8, 0.85, 0.9];
        subDoc.applyFill = true;
        subDoc.font = "ArialMT";
        subDoc.justification = ParagraphJustification.LEFT_JUSTIFY;
        subTextProp.setValue(subDoc);

        var subPos = subLayer.property("ADBE Transform Group").property("ADBE Position");
        subPos.setValue([marginX + 30, marginY + 28]);

        // 3. Auto-sizing Background Shape Layer
        var shapeLayer = comp.layers.addShape();
        shapeLayer.name = "LT_Background_Box";
        shapeLayer.moveAfter(subLayer); // place behind text layers

        var shapeGroups = shapeLayer.property("ADBE Root Vectors Group");
        var boxGroup = shapeGroups.addProperty("ADBE Vector Group");
        boxGroup.name = "Box Group";

        var boxContents = boxGroup.property("ADBE Vectors Group");
        var rectShape = boxContents.addProperty("ADBE Vector Shape - Rect");
        var rectFill = boxContents.addProperty("ADBE Vector Graphic - Fill");
        var rectStroke = boxContents.addProperty("ADBE Vector Graphic - Stroke");

        // Set styling
        rectFill.property("ADBE Vector Fill Color").setValue([0.08, 0.12, 0.18, 1.0]); // Deep dark navy
        rectFill.property("ADBE Vector Fill Opacity").setValue(90);

        rectStroke.property("ADBE Vector Stroke Color").setValue([0.2, 0.6, 1.0, 1.0]); // Electric blue accent
        rectStroke.property("ADBE Vector Stroke Width").setValue(3);

        // Rounded corners
        rectShape.property("ADBE Vector Rect Roundness").setValue(12);

        // Dynamic size expression based on text sourceRectAtTime
        var sizeExpr = 
            'var padX = 40;\n' +
            'var padY = 20;\n' +
            'var tL = thisComp.layer("LT_Title");\n' +
            'var sL = thisComp.layer("LT_Subtitle");\n' +
            'var r1 = tL.sourceRectAtTime(time, false);\n' +
            'var r2 = sL.sourceRectAtTime(time, false);\n' +
            'var totalW = Math.max(r1.width, r2.width) + padX * 2;\n' +
            'var totalH = (r1.height + r2.height + 25) + padY * 2;\n' +
            '[totalW, totalH];';
        rectShape.property("ADBE Vector Rect Size").expression = sizeExpr;

        // Dynamic position expression aligning box with text
        var posExpr = 
            'var padX = 40;\n' +
            'var padY = 20;\n' +
            'var tL = thisComp.layer("LT_Title");\n' +
            'var sL = thisComp.layer("LT_Subtitle");\n' +
            'var r1 = tL.sourceRectAtTime(time, false);\n' +
            'var r2 = sL.sourceRectAtTime(time, false);\n' +
            'var totalW = Math.max(r1.width, r2.width) + padX * 2;\n' +
            'var totalH = (r1.height + r2.height + 25) + padY * 2;\n' +
            'var leftEdge = tL.transform.position[0] - padX;\n' +
            'var topEdge = tL.transform.position[1] + r1.top - padY;\n' +
            '[leftEdge + totalW / 2, topEdge + totalH / 2];';
        shapeLayer.property("ADBE Transform Group").property("ADBE Position").expression = posExpr;

        // 4. Smooth In/Out Animations (Opacity & X-translation)
        var parentNull = comp.layers.addNull();
        parentNull.name = "LT_Master_Controller";
        parentNull.property("ADBE Transform Group").property("ADBE Position").setValue([0, 0]);

        // Parent all elements to Master Null
        titleLayer.parent = parentNull;
        subLayer.parent = parentNull;
        shapeLayer.parent = parentNull;

        var nullPos = parentNull.property("ADBE Transform Group").property("ADBE Position");
        var nullOpacity = parentNull.property("ADBE Transform Group").property("ADBE Opacity");

        // Keyframe intro (0s to 0.6s)
        var tStart = comp.workAreaStart;
        nullPos.setValueAtTime(tStart, [-150, 0]);
        nullPos.setValueAtTime(tStart + 0.6, [0, 0]);
        nullOpacity.setValueAtTime(tStart, 0);
        nullOpacity.setValueAtTime(tStart + 0.4, 100);

        // Smooth easing keyframes
        var easeIn = new KeyframeEase(0, 75);
        var easeOut = new KeyframeEase(0, 75);
        for (var k = 1; k <= nullPos.numKeys; k++) {
            nullPos.setTemporalEaseAtKey(k, [easeIn, easeIn, easeIn], [easeOut, easeOut, easeOut]);
        }

        app.endUndoGroup();

        return {
            status: "success",
            message: "Dynamic lower third created successfully with auto-sizing sourceRectAtTime expressions.",
            controllerLayer: parentNull.index,
            titleLayer: titleLayer.index,
            subtitleLayer: subLayer.index,
            backgroundLayer: shapeLayer.index
        };
    } catch (e) {
        app.endUndoGroup();
        throw e;
    }
})();
