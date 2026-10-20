FeatureScript 3083;
import(path : "onshape/std/common.fs", version : "3083.0");

const ARC_ANGLE_BOUNDS = { (degree) : [0.01, 20, 359.99] } as AngleBoundSpec;
const ARC_RADIUS_BOUNDS = { (inch) : [0.001, 20, 10000] } as LengthBoundSpec;
const ARC_THICKNESS_BOUNDS = { (inch) : [0.001, 0.5, 10000] } as LengthBoundSpec;

annotation { "Feature Type Name" : "Center Arc" }
export const centerArc = defineFeature(function(context is Context, id is Id, definition is map)
    precondition
    {
        annotation { "Name" : "Sweep angle" }
        isAngle(definition.sweepAngle, ARC_ANGLE_BOUNDS);

        annotation { "Name" : "Radius" }
        isLength(definition.radius, ARC_RADIUS_BOUNDS);

        annotation { "Name" : "Thickness" }
        isLength(definition.thickness, ARC_THICKNESS_BOUNDS);
    }
    {
        const halfThickness = definition.thickness / 2;
        const innerRadius = definition.radius - halfThickness;
        const outerRadius = definition.radius + halfThickness;
        const halfAngle = definition.sweepAngle / 2;
        const endAngle = definition.sweepAngle;

        const arcSketch = newSketch(context, id + "arcSketch", {
            "sketchPlane" : qCreatedBy(makeId("Top"), EntityType.FACE)
        });

        skArc(arcSketch, "innerOffsetArc", {
            "start" : vector(innerRadius, 0 * inch),
            "mid" : vector(innerRadius * cos(halfAngle), innerRadius * sin(halfAngle)),
            "end" : vector(innerRadius * cos(endAngle), innerRadius * sin(endAngle))
        });

        skArc(arcSketch, "centerConstructionArc", {
            "start" : vector(definition.radius, 0 * inch),
            "mid" : vector(definition.radius * cos(halfAngle), definition.radius * sin(halfAngle)),
            "end" : vector(definition.radius * cos(endAngle), definition.radius * sin(endAngle)),
            "construction" : true
        });

        skArc(arcSketch, "outerOffsetArc", {
            "start" : vector(outerRadius, 0 * inch),
            "mid" : vector(outerRadius * cos(halfAngle), outerRadius * sin(halfAngle)),
            "end" : vector(outerRadius * cos(endAngle), outerRadius * sin(endAngle))
        });

        skLineSegment(arcSketch, "startConnector", {
            "start" : vector(innerRadius, 0 * inch),
            "end" : vector(outerRadius, 0 * inch)
        });

        skLineSegment(arcSketch, "endConnector", {
            "start" : vector(innerRadius * cos(endAngle), innerRadius * sin(endAngle)),
            "end" : vector(outerRadius * cos(endAngle), outerRadius * sin(endAngle))
        });

        skSolve(arcSketch);

        opExtrude(context, id + "baseExtrude", {
            "entities" : qSketchRegion(id + "arcSketch"),
            "direction" : vector(0, 0, 1),
            "endBound" : BoundingType.BLIND,
            "endDepth" : 5 * inch
        });

        const innerStartPoint = vector(innerRadius, 0 * inch, 0 * inch);
        const innerEndPoint = vector(innerRadius * cos(endAngle), innerRadius * sin(endAngle), 0 * inch);
        const topInnerStartPoint = innerStartPoint + vector(0 * inch, 0 * inch, 5 * inch);
        const chordDirection = innerEndPoint - innerStartPoint;
        const extrusionDirection = topInnerStartPoint - innerStartPoint;
        const insidePlaneNormal = cross(chordDirection, extrusionDirection);
        const insidePlane = plane(innerStartPoint, insidePlaneNormal, chordDirection);

        opPlane(context, id + "insideReferencePlane", {
            "plane" : insidePlane
        });
    }, {
        "sweepAngle" : 20 * degree,
        "radius" : 20 * inch,
        "thickness" : 0.5 * inch
    });
