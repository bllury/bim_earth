import * as Cesium from 'cesium'

export const MIN_MODEL_SCALE = 0.01
export const MAX_MODEL_SCALE = 100
export const SLIDER_MAX_MODEL_SCALE = 100
export const SLIDER_MIN_MODEL_SCALE = 0.1
export const SLIDER_STEP = 0.1

export interface ModelTransformInput {
  longitude: number
  latitude: number
  height?: number
  scale?: number
  localVerticalMinimum?: number
  rotationZ?: number
}

export const createModelTransform = (
  input: ModelTransformInput,
  result = new Cesium.Matrix4(),
) => {
  const {
    longitude,
    latitude,
    height = 0,
    scale = 1,
    localVerticalMinimum = 0,
    rotationZ = 0,
  } = input

  const origin = Cesium.Cartesian3.fromDegrees(longitude, latitude, height)
  const eastNorthUp = Cesium.Transforms.eastNorthUpToFixedFrame(origin)
  const uniformScale = Cesium.Matrix4.fromUniformScale(scale)
  const rotation = Cesium.Matrix4.fromRotationTranslation(
    Cesium.Matrix3.fromRotationZ(Cesium.Math.toRadians(rotationZ)),
    Cesium.Cartesian3.ZERO,
    new Cesium.Matrix4(),
  )
  const verticalOffset = -localVerticalMinimum * scale
  const translation = Cesium.Matrix4.fromTranslation(
    new Cesium.Cartesian3(0, 0, verticalOffset),
  )

  const localTransform = new Cesium.Matrix4()
  Cesium.Matrix4.multiply(rotation, uniformScale, localTransform)
  Cesium.Matrix4.multiply(translation, localTransform, localTransform)

  return Cesium.Matrix4.multiply(eastNorthUp, localTransform, result)
}

/** Converts a world-space point into the model's local coordinate system. */
export const worldPointToModel = (
  modelMatrix: Cesium.Matrix4,
  worldPoint: Cesium.Cartesian3,
  result = new Cesium.Cartesian3(),
) => {
  const inverseMatrix = Cesium.Matrix4.inverse(
    modelMatrix,
    new Cesium.Matrix4(),
  )
  return Cesium.Matrix4.multiplyByPoint(inverseMatrix, worldPoint, result)
}
