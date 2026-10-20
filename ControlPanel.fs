FeatureScript 3095;
import(path : "onshape/std/common.fs", version : "3095.0");

const PANEL_X_SIZE_BOUNDS = { (inch) : [0.001, 12, 1000] } as LengthBoundSpec;
const PANEL_Y_SIZE_BOUNDS = { (inch) : [0.001, 8, 1000] } as LengthBoundSpec;

annotation { "Feature Type Name" : "Control Panel" }
export const controlPanel = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "X size" }
        isLength(definition.xSize, PANEL_X_SIZE_BOUNDS);

        annotation { "Name" : "Y size" }
        isLength(definition.ySize, PANEL_Y_SIZE_BOUNDS);
    }
    {
        const halfX = definition.xSize / 2;
        const halfY = definition.ySize / 2;

        const panelSketch = newSketch(context, id + "panelSketch", {
            "sketchPlane" : qCreatedBy(makeId("Top"), EntityType.FACE)
        });

        skRectangle(panelSketch, "controlPanelRectangle", {
            "firstCorner" : vector(-halfX, -halfY),
            "secondCorner" : vector(halfX, halfY)
        });

        skSolve(panelSketch);
    }, {
        "xSize" : 12 * inch,
        "ySize" : 8 * inch
    });
