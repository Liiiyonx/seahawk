/**
 * 后期处理管线：HDR UnrealBloom + MSAA 前向合成
 *
 * 参考 three.js 官方示例 webgl_postprocessing_unreal_bloom 的管线结构：
 *   RenderPass → UnrealBloomPass → OutputPass
 * 其中 OutputPass 是必须的：renderer 渲染到 RenderTarget 时不做色调映射，
 * 由 OutputPass 在最后统一做 ACES + sRGB 转换，否则画面会发灰/过曝。
 *
 * 泛光在沙盘里的作用 —— 让"发光语义"真正成立：
 *   - 阳光海面碎钻（>1 的镜面高光先晕开再压缩，才有波光粼粼）
 *   - 船体航行灯 / 事件光柱 / 目标浮标脉冲（辉光让远距目标一眼可辨）
 * 这是从"能看"到"高级"的关键一步。
 */

import * as THREE from 'three'
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js'

export class PostFX {
  /**
   * @param {THREE.WebGLRenderer} renderer
   * @param {THREE.Scene} scene
   * @param {THREE.Camera} camera
   */
  constructor(renderer, scene, camera) {
    const size = renderer.getDrawingBufferSize(new THREE.Vector2())

    // HalfFloat RT 承载 HDR 亮度（泛光阈值以上的值不能被 8bit 截断）；
    // samples:4 = WebGL2 MSAA —— composer 会绕过 canvas 的 antialias 参数，必须显式开
    const rt = new THREE.WebGLRenderTarget(Math.max(2, size.x), Math.max(2, size.y), {
      type: THREE.HalfFloatType,
      samples: 4,
    })

    this.composer = new EffectComposer(renderer, rt)
    this.composer.addPass(new RenderPass(scene, camera))

    // (resolution, strength, radius, threshold)
    // 阈值 0.85：只让真正的高光参与泛光（阳光/碎钻/灯光），避免整幅画面发糊
    this.bloom = new UnrealBloomPass(
      new THREE.Vector2(Math.max(2, size.x), Math.max(2, size.y)),
      0.55,
      0.5,
      0.85,
    )
    this.composer.addPass(this.bloom)
    this.composer.addPass(new OutputPass())
  }

  setSize(width, height) {
    this.composer.setSize(width, height)
  }

  setPixelRatio(ratio) {
    this.composer.setPixelRatio(ratio)
  }

  render() {
    this.composer.render()
  }

  dispose() {
    for (const pass of this.composer.passes) pass.dispose?.()
    this.composer.renderTarget1?.dispose()
    this.composer.renderTarget2?.dispose()
  }
}