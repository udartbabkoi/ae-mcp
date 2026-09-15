/**
 * dom_helpers.jsx - Core ExtendScript DOM Utilities for ae-mcp.
 * Strict ES3 JavaScript compatible (No let, const, arrow functions, or template strings).
 * Uses language-invariant match names throughout.
 */

var AEDomHelpers = (function () {
    "use strict";

    // Match name dictionary constants
    var MATCH = {
        TRANSFORM: "ADBE Transform Group",
        POSITION: "ADBE Position",
        SCALE: "ADBE Scale",
        ROTATION: "ADBE Rotate Z",
        OPACITY: "ADBE Opacity",
        ANCHOR_POINT: "ADBE Anchor Point",
        MASK_PARADE: "ADBE Mask Parade",
        MASK_ATOM: "ADBE Mask Atom",
        MASK_SHAPE: "ADBE Mask Shape",
        MASK_FEATHER: "ADBE Mask Feather",
        MASK_OPACITY: "ADBE Mask Opacity",
        ROOT_VECTORS: "ADBE Root Vectors Group",
        VECTOR_GROUP: "ADBE Vector Group",
        VECTORS_GROUP: "ADBE Vectors Group",
        RECT_SHAPE: "ADBE Vector Shape - Rect",
        ELLIPSE_SHAPE: "ADBE Vector Shape - Ellipse",
        FILL: "ADBE Vector Graphic - Fill",
        STROKE: "ADBE Vector Graphic - Stroke"
    };

    /**
     * Defensive validation for active composition.
     */
    function getActiveComp() {
        if (!app.project) {
            throw new Error("No project is currently open in After Effects.");
        }
        var activeItem = app.project.activeItem;
        if (!activeItem || !(activeItem instanceof CompItem)) {
            throw new Error("No active composition selected or open. Please open a composition in the viewer.");
        }
        return activeItem;
    }

    /**
     * Determine descriptive human-readable layer type.
     */
    function getLayerType(layer) {
        if (layer.nullLayer) return "Null";
        if (layer.adjustmentLayer) return "Adjustment";
        if (layer.guideLayer) return "Guide";
        if (layer instanceof ShapeLayer) return "Shape";
        if (layer instanceof TextLayer) return "Text";
        if (layer instanceof CameraLayer) return "Camera";
        if (layer instanceof LightLayer) return "Light";
        if (layer instanceof AVLayer) {
            if (layer.source) {
                if (layer.source instanceof CompItem) return "Precomp";
                if (layer.source.mainSource) {
                    if (layer.source.mainSource instanceof SolidSource) return "Solid";
                    if (layer.source.mainSource instanceof FileSource) return "Footage";
                    if (layer.source.mainSource instanceof PlaceholderSource) return "Placeholder";
                }
            }
            return "AVLayer";
        }
        return "Unknown";
    }

    /**
     * Introspect all masks on a layer via ADBE Mask Parade.
     */
    function getLayerMasks(layer) {
        var masksList = [];
        var maskParade = layer.property(MATCH.MASK_PARADE);
        if (!maskParade) return masksList;

        var numMasks = maskParade.numProperties;
        for (var i = 1; i <= numMasks; i++) {
            var mask = maskParade.property(i);
            var modeStr = "NONE";
            switch (mask.maskMode) {
                case MaskMode.NONE: modeStr = "NONE"; break;
                case MaskMode.ADD: modeStr = "ADD"; break;
                case MaskMode.SUBTRACT: modeStr = "SUBTRACT"; break;
                case MaskMode.INTERSECT: modeStr = "INTERSECT"; break;
                case MaskMode.LIGHTEN: modeStr = "LIGHTEN"; break;
                case MaskMode.DARKEN: modeStr = "DARKEN"; break;
                case MaskMode.DIFFERENCE: modeStr = "DIFFERENCE"; break;
            }

            var maskShapeProp = mask.property(MATCH.MASK_SHAPE);
            var vertCount = 0;
            var isClosed = true;
            if (maskShapeProp && maskShapeProp.value) {
                var s = maskShapeProp.value;
                if (s.vertices) vertCount = s.vertices.length;
                if (s.closed !== undefined) isClosed = s.closed;
            }

            var featherProp = mask.property(MATCH.MASK_FEATHER);
            var opacityProp = mask.property(MATCH.MASK_OPACITY);

            masksList.push({
                index: i,
                name: mask.name,
                maskMode: modeStr,
                inverted: mask.inverted ? true : false,
                rotoBezier: mask.rotoBezier ? true : false,
                closed: isClosed,
                numVertices: vertCount,
                feather: featherProp ? featherProp.value : [0, 0],
                opacity: opacityProp ? opacityProp.value : 100
            });
        }
        return masksList;
    }

    /**
     * Extract full active composition state including all layers and properties.
     */
    function getActiveCompState() {
        var comp = getActiveComp();
        var layersData = [];

        for (var i = 1; i <= comp.numLayers; i++) {
            var layer = comp.layer(i);

            // Track matte status (supporting both modern AE 2023+ and legacy)
            var matteTypeStr = "NONE";
            var matteLayerIndex = null;

            if (layer.trackMatteType !== undefined) {
                switch (layer.trackMatteType) {
                    case TrackMatteType.NO_TRACK_MATTE: matteTypeStr = "NO_TRACK_MATTE"; break;
                    case TrackMatteType.ALPHA: matteTypeStr = "ALPHA"; break;
                    case TrackMatteType.NOT_ALPHA: matteTypeStr = "NOT_ALPHA"; break;
                    case TrackMatteType.LUMA: matteTypeStr = "LUMA"; break;
                    case TrackMatteType.NOT_LUMA: matteTypeStr = "NOT_LUMA"; break;
                }
            }

            // AE 2023+ (v23.0+) trackMatteLayer property
            if (layer.trackMatteLayer !== undefined && layer.trackMatteLayer !== null) {
                matteLayerIndex = layer.trackMatteLayer.index;
            }

            // Source file path if footage
            var sourceFilePath = null;
            if (layer.source && layer.source.file) {
                sourceFilePath = layer.source.file.fsName;
            }

            // Layer transform dimensions
            var lWidth = layer.width !== undefined ? layer.width : comp.width;
            var lHeight = layer.height !== undefined ? layer.height : comp.height;

            layersData.push({
                index: layer.index,
                name: layer.name,
                type: getLayerType(layer),
                inPoint: Math.round(layer.inPoint * 1000) / 1000,
                outPoint: Math.round(layer.outPoint * 1000) / 1000,
                startTime: Math.round(layer.startTime * 1000) / 1000,
                enabled: layer.enabled ? true : false,
                locked: layer.locked ? true : false,
                shy: layer.shy ? true : false,
                solo: layer.solo ? true : false,
                hasVideo: layer.hasVideo ? true : false,
                hasAudio: layer.hasAudio ? true : false,
                parentIndex: layer.parent ? layer.parent.index : null,
                width: lWidth,
                height: lHeight,
                sourceFilePath: sourceFilePath,
                trackMatte: {
                    type: matteTypeStr,
                    matteLayerIndex: matteLayerIndex,
                    hasTrackMatte: layer.hasTrackMatte ? true : false
                },
                masks: getLayerMasks(layer)
            });
        }

        return {
            name: comp.name,
            id: comp.id,
            width: comp.width,
            height: comp.height,
            pixelAspect: comp.pixelAspect,
            frameRate: comp.frameRate,
            frameDuration: comp.frameDuration,
            duration: Math.round(comp.duration * 1000) / 1000,
            workAreaStart: Math.round(comp.workAreaStart * 1000) / 1000,
            workAreaDuration: Math.round(comp.workAreaDuration * 1000) / 1000,
            currentTime: Math.round(comp.time * 1000) / 1000,
            numLayers: comp.numLayers,
            layers: layersData
        };
    }

    /**
     * Injects a vector mask path into ADBE Mask Parade using Shape() object.
     */
    function createMaskPath(layerIndex, vertices, inTangents, outTangents, maskModeStr, feather, closed) {
        var comp = getActiveComp();
        if (layerIndex < 1 || layerIndex > comp.numLayers) {
            throw new Error("Layer index " + layerIndex + " is out of bounds (1 to " + comp.numLayers + ").");
        }
        var layer = comp.layer(layerIndex);

        var maskParade = layer.property(MATCH.MASK_PARADE);
        if (!maskParade) {
            throw new Error("Target layer does not support mask operations.");
        }

        var mask = maskParade.addProperty(MATCH.MASK_ATOM);
        if (!mask) {
            throw new Error("Failed to add mask property to layer.");
        }

        // Configure mask mode
        var modeUpper = String(maskModeStr || "ADD").toUpperCase();
        switch (modeUpper) {
            case "NONE": mask.maskMode = MaskMode.NONE; break;
            case "ADD": mask.maskMode = MaskMode.ADD; break;
            case "SUBTRACT": mask.maskMode = MaskMode.SUBTRACT; break;
            case "INTERSECT": mask.maskMode = MaskMode.INTERSECT; break;
            case "LIGHTEN": mask.maskMode = MaskMode.LIGHTEN; break;
            case "DARKEN": mask.maskMode = MaskMode.DARKEN; break;
            case "DIFFERENCE": mask.maskMode = MaskMode.DIFFERENCE; break;
            default: mask.maskMode = MaskMode.ADD;
        }

        // Construct Shape
        var myShape = new Shape();
        myShape.vertices = vertices;
        if (inTangents && inTangents.length === vertices.length) {
            myShape.inTangents = inTangents;
        }
        if (outTangents && outTangents.length === vertices.length) {
            myShape.outTangents = outTangents;
        }
        myShape.closed = (closed !== false);

        var maskShapeProp = mask.property(MATCH.MASK_SHAPE);
        maskShapeProp.setValue(myShape);

        if (feather && feather.length === 2) {
            var featherProp = mask.property(MATCH.MASK_FEATHER);
            if (featherProp) {
                featherProp.setValue([feather[0], feather[1]]);
            }
        }

        return {
            success: true,
            maskIndex: mask.propertyIndex,
            maskName: mask.name,
            maskMode: modeUpper,
            vertexCount: vertices.length,
            closed: myShape.closed
        };
    }

    /**
     * Modern and legacy track matte application.
     */
    function applyTrackMatte(targetLayer, matteLayer, matteType) {
        if (!matteType) matteType = TrackMatteType.ALPHA;

        if (typeof targetLayer.setTrackMatte === "function") {
            // Modern AE 2023+ (v23.0+)
            targetLayer.setTrackMatte(matteLayer, matteType);
            return "modern_setTrackMatte";
        } else {
            // Legacy AE: matteLayer must be immediately above targetLayer
            matteLayer.moveBefore(targetLayer);
            targetLayer.trackMatteType = matteType;
            return "legacy_trackMatteType";
        }
    }

    return {
        MATCH: MATCH,
        getActiveComp: getActiveComp,
        getActiveCompState: getActiveCompState,
        createMaskPath: createMaskPath,
        applyTrackMatte: applyTrackMatte
    };
})();
