from __future__ import annotations

import html
import json
from uuid import uuid4


def pixi_badge_runtime_html() -> str:
    return '''
    <script src="https://cdn.jsdelivr.net/npm/pixi.js@8.9.2/dist/pixi.min.js"></script>
    <script>
    (() => {
      if (window.__trkPixiBadgeRuntimeInstalled) return;
      window.__trkPixiBadgeRuntimeInstalled = true;

      const BADGE_PRESETS = {
        diamond: {
          shape: 'diamond',
          effect: 'cosmic',
          colors: { coreStart: '#ffffff', coreEnd: '#172554', edge: '#d8fbff', shadow: '#0f172a', auraInner: '#ecfeff', auraOuter: '#2563eb', text: '#ffffff' },
          metrics: { coreScale: 0.58, innerAura: 0.62, outerAura: 1.24, ring: 0.34 },
          defaults: { energy: 1.18, motion: 1.08, particles: 0.94, contrast: 1.12 },
        },
        ruby: {
          shape: 'crown',
          effect: 'flame',
          colors: { coreStart: '#ffe4ea', coreEnd: '#4c0519', edge: '#fda4af', shadow: '#2a0713', auraInner: '#fecdd3', auraOuter: '#be123c', text: '#fff3f5' },
          metrics: { coreScale: 0.57, innerAura: 0.58, outerAura: 1.18, ring: 0.33 },
          defaults: { energy: 1.08, motion: 1.28, particles: 0.82, contrast: 1.06 },
        },
        sapphire: {
          shape: 'shard',
          effect: 'orbit',
          colors: { coreStart: '#eff6ff', coreEnd: '#1e3a8a', edge: '#bfdbfe', shadow: '#082f49', auraInner: '#dbeafe', auraOuter: '#2563eb', text: '#ffffff' },
          metrics: { coreScale: 0.56, innerAura: 0.56, outerAura: 1.12, ring: 0.34 },
          defaults: { energy: 0.98, motion: 0.84, particles: 0.54, contrast: 1.04 },
        },
        amethyst: {
          shape: 'hex',
          effect: 'rune',
          colors: { coreStart: '#faf5ff', coreEnd: '#2e1065', edge: '#e9d5ff', shadow: '#1e1032', auraInner: '#f3e8ff', auraOuter: '#7e22ce', text: '#ffffff' },
          metrics: { coreScale: 0.55, innerAura: 0.54, outerAura: 1.1, ring: 0.35 },
          defaults: { energy: 0.9, motion: 0.78, particles: 0.64, contrast: 0.98 },
        },
        emerald: {
          shape: 'seal',
          effect: 'nature',
          colors: { coreStart: '#ecfdf5', coreEnd: '#064e3b', edge: '#a7f3d0', shadow: '#052e2b', auraInner: '#d1fae5', auraOuter: '#059669', text: '#f0fdf4' },
          metrics: { coreScale: 0.56, innerAura: 0.53, outerAura: 1.06, ring: 0.34 },
          defaults: { energy: 0.88, motion: 0.74, particles: 0.58, contrast: 0.98 },
        },
        gold: {
          shape: 'round',
          effect: 'solar',
          colors: { coreStart: '#fff7d6', coreEnd: '#78350f', edge: '#fde68a', shadow: '#422006', auraInner: '#fef3c7', auraOuter: '#d97706', text: '#fff8e5' },
          metrics: { coreScale: 0.54, innerAura: 0.51, outerAura: 1.02, ring: 0.34 },
          defaults: { energy: 0.84, motion: 0.68, particles: 0.48, contrast: 0.96 },
        },
        topaz: {
          shape: 'square',
          effect: 'seam',
          colors: { coreStart: '#fff3cf', coreEnd: '#451a03', edge: '#fcd34d', shadow: '#2b1205', auraInner: '#fde68a', auraOuter: '#b45309', text: '#fff7de' },
          metrics: { coreScale: 0.53, innerAura: 0.48, outerAura: 0.96, ring: 0.32 },
          defaults: { energy: 0.76, motion: 0.62, particles: 0.32, contrast: 0.94 },
        },
        silver: {
          shape: 'round',
          effect: 'metal',
          colors: { coreStart: '#f8fafc', coreEnd: '#475569', edge: '#e2e8f0', shadow: '#1e293b', auraInner: '#e2e8f0', auraOuter: '#94a3b8', text: '#ffffff' },
          metrics: { coreScale: 0.52, innerAura: 0.46, outerAura: 0.9, ring: 0.33 },
          defaults: { energy: 0.68, motion: 0.48, particles: 0.2, contrast: 0.92 },
        },
        aquamarine: {
          shape: 'shield',
          effect: 'wave',
          colors: { coreStart: '#ecfeff', coreEnd: '#0f3a46', edge: '#a5f3fc', shadow: '#083344', auraInner: '#cffafe', auraOuter: '#0891b2', text: '#f0fdff' },
          metrics: { coreScale: 0.52, innerAura: 0.47, outerAura: 0.92, ring: 0.32 },
          defaults: { energy: 0.72, motion: 0.56, particles: 0.3, contrast: 0.94 },
        },
        jade: {
          shape: 'shield',
          effect: 'fog',
          colors: { coreStart: '#edf6ea', coreEnd: '#24311d', edge: '#b5c4a1', shadow: '#172012', auraInner: '#d6e2cb', auraOuter: '#4a7c40', text: '#f4faef' },
          metrics: { coreScale: 0.5, innerAura: 0.44, outerAura: 0.86, ring: 0.31 },
          defaults: { energy: 0.58, motion: 0.38, particles: 0.14, contrast: 0.9 },
        },
        garnet: {
          shape: 'cracked',
          effect: 'collapse',
          colors: { coreStart: '#fee2e2', coreEnd: '#450a0a', edge: '#fca5a5', shadow: '#240808', auraInner: '#fecaca', auraOuter: '#b91c1c', text: '#fff5f5' },
          metrics: { coreScale: 0.51, innerAura: 0.43, outerAura: 0.88, ring: 0.3 },
          defaults: { energy: 0.7, motion: 0.82, particles: 0.36, contrast: 0.96 },
        },
        onyx: {
          shape: 'slab',
          effect: 'shadow',
          colors: { coreStart: '#80838b', coreEnd: '#09090b', edge: '#3f3f46', shadow: '#020204', auraInner: '#3f3f46', auraOuter: '#111827', text: '#e5e7eb' },
          metrics: { coreScale: 0.5, innerAura: 0.38, outerAura: 0.72, ring: 0.29 },
          defaults: { energy: 0.36, motion: 0.22, particles: 0.04, contrast: 0.88 },
        },
        low: {
          shape: 'pill',
          effect: 'void',
          colors: { coreStart: '#3f3f46', coreEnd: '#050507', edge: '#1f2937', shadow: '#000000', auraInner: '#15171b', auraOuter: '#020203', text: '#cbd5e1' },
          metrics: { coreScale: 0.48, innerAura: 0.3, outerAura: 0.58, ring: 0.28 },
          defaults: { energy: 0.18, motion: 0.0, particles: 0.0, contrast: 0.86 },
        },
      };

      function clone(value) {
        return JSON.parse(JSON.stringify(value));
      }

      function mergeConfig(base, override) {
        const merged = clone(base);
        if (!override || typeof override !== 'object') return merged;
        Object.entries(override).forEach(([key, value]) => {
          if (value && typeof value === 'object' && !Array.isArray(value) && merged[key] && typeof merged[key] === 'object' && !Array.isArray(merged[key])) {
            merged[key] = mergeConfig(merged[key], value);
            return;
          }
          merged[key] = value;
        });
        return merged;
      }

      function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
      }

      function toRgba(hex, alpha) {
        const normalized = String(hex || '#ffffff').replace('#', '');
        const source = normalized.length === 3
          ? normalized.split('').map((ch) => ch + ch).join('')
          : normalized.padEnd(6, '0').slice(0, 6);
        const intValue = parseInt(source, 16);
        const r = (intValue >> 16) & 255;
        const g = (intValue >> 8) & 255;
        const b = intValue & 255;
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
      }

      function toHexInt(hex) {
        return parseInt(String(hex || '#ffffff').replace('#', ''), 16);
      }

      function makeRadialTexture(inner, outer, size = 256, mid = null) {
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
        gradient.addColorStop(0, inner);
        if (mid) {
          gradient.addColorStop(0.45, mid);
        } else {
          gradient.addColorStop(0.35, inner);
        }
        gradient.addColorStop(1, outer);
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, size, size);
        return PIXI.Texture.from(canvas);
      }

      function makeBeamTexture(palette, length = 280, width = 52) {
        const canvas = document.createElement('canvas');
        canvas.width = length;
        canvas.height = width;
        const ctx = canvas.getContext('2d');
        const gradient = ctx.createLinearGradient(0, width / 2, length, width / 2);
        gradient.addColorStop(0, 'rgba(255,255,255,0)');
        gradient.addColorStop(0.22, toRgba(palette.edge, 0.92));
        gradient.addColorStop(0.48, toRgba(palette.auraInner, 0.82));
        gradient.addColorStop(0.82, toRgba(palette.auraOuter, 0.26));
        gradient.addColorStop(1, toRgba(palette.auraOuter, 0));
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.moveTo(0, width / 2);
        ctx.lineTo(length * 0.14, width * 0.14);
        ctx.lineTo(length, width / 2);
        ctx.lineTo(length * 0.14, width * 0.86);
        ctx.closePath();
        ctx.fill();
        return PIXI.Texture.from(canvas);
      }

      function shapePoints(shape, size) {
        const half = size / 2;
        const points = {
          diamond: [[0, -half], [half * 0.7, 0], [0, half], [-half * 0.7, 0]],
          crown: [[0, -half], [half * 0.28, -half * 0.22], [half * 0.75, -half * 0.1], [half * 0.56, half * 0.45], [0, half], [-half * 0.56, half * 0.45], [-half * 0.75, -half * 0.1], [-half * 0.28, -half * 0.22]],
          shard: [[0, -half], [half * 0.58, -half * 0.12], [half * 0.3, half], [-half * 0.28, half], [-half * 0.6, -half * 0.08]],
          hex: [[0, -half], [half * 0.82, -half * 0.45], [half * 0.82, half * 0.45], [0, half], [-half * 0.82, half * 0.45], [-half * 0.82, -half * 0.45]],
          square: [[-half * 0.82, -half * 0.82], [half * 0.82, -half * 0.82], [half * 0.82, half * 0.82], [-half * 0.82, half * 0.82]],
          shield: [[0, -half], [half * 0.76, -half * 0.44], [half * 0.62, half * 0.42], [0, half], [-half * 0.62, half * 0.42], [-half * 0.76, -half * 0.44]],
          cracked: [[0, -half], [half * 0.82, -half * 0.2], [half * 0.5, half], [-half * 0.24, half * 0.74], [-half * 0.82, half * 0.16], [-half * 0.52, -half * 0.62]],
          slab: [[-half * 0.9, -half * 0.62], [half * 0.9, -half * 0.62], [half * 0.9, half * 0.62], [-half * 0.9, half * 0.62]],
          pill: [[-half * 0.96, -half * 0.42], [half * 0.96, -half * 0.42], [half * 0.96, half * 0.42], [-half * 0.96, half * 0.42]],
        };
        return points[shape] || points.round;
      }

      function drawPolygon(ctx, points) {
        ctx.beginPath();
        ctx.moveTo(points[0][0], points[0][1]);
        for (let i = 1; i < points.length; i++) {
          ctx.lineTo(points[i][0], points[i][1]);
        }
        ctx.closePath();
      }

      function drawCoreTexture(config, size, contrast) {
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        ctx.save();
        ctx.translate(size / 2, size / 2);
        const gradient = ctx.createLinearGradient(-size / 2, -size / 2, size / 2, size / 2);
        gradient.addColorStop(0, config.colors.coreStart);
        gradient.addColorStop(0.36, toRgba(config.colors.auraInner, 0.94));
        gradient.addColorStop(1, config.colors.coreEnd);

        if (config.shape === 'round') {
          ctx.beginPath();
          ctx.arc(0, 0, size * 0.38, 0, Math.PI * 2);
        } else if (config.shape === 'seal') {
          ctx.beginPath();
          ctx.arc(0, 0, size * 0.36, 0, Math.PI * 2);
        } else if (config.shape === 'pill') {
          const width = size * 0.82;
          const height = size * 0.4;
          const radius = height / 2;
          ctx.beginPath();
          ctx.roundRect(-width / 2, -height / 2, width, height, radius);
        } else if (config.shape === 'slab') {
          const width = size * 0.78;
          const height = size * 0.52;
          ctx.beginPath();
          ctx.roundRect(-width / 2, -height / 2, width, height, size * 0.08);
        } else if (config.shape === 'diamond') {
          const w = size * 0.45;
          const h = size * 0.6;
          const tW = w * 0.6;
          const cH = h * 0.25;

          // Replace the default 2D gradient drawing with the explicit layered faceted method from user
          ctx.fillStyle = '#d97e26';
          ctx.beginPath(); ctx.moveTo(-w, -h/2+cH); ctx.lineTo(w, -h/2+cH); ctx.lineTo(0, h/2); ctx.fill();
          
          ctx.fillStyle = 'rgba(179, 98, 29, 0.6)';
          ctx.beginPath(); ctx.moveTo(0, -h/2+cH); ctx.lineTo(w, -h/2+cH); ctx.lineTo(0, h/2); ctx.fill();

          ctx.fillStyle = '#ffa545';
          ctx.beginPath(); ctx.moveTo(-tW, -h/2); ctx.lineTo(tW, -h/2); ctx.lineTo(w, -h/2+cH); ctx.lineTo(-w, -h/2+cH); ctx.fill();

          ctx.fillStyle = '#fff0ad';
          ctx.beginPath(); ctx.moveTo(-tW+10, -h/2+5); ctx.lineTo(tW-10, -h/2+5); ctx.lineTo(tW+5, -h/2+15); ctx.lineTo(-tW-5, -h/2+15); ctx.fill();

          // Standardize path so the later lines can stroke the edges
          ctx.beginPath();
          drawPolygon(ctx, [ [0, -h/2], [w, -h/2+cH], [0, h/2], [-w, -h/2+cH] ]);
        } else {
          drawPolygon(ctx, shapePoints(config.shape, size * 0.84));
        }

        ctx.fillStyle = gradient;
        ctx.fill();
        ctx.lineWidth = 6 * contrast;
        ctx.strokeStyle = config.colors.edge;
        ctx.stroke();
        ctx.globalAlpha = 0.46 * contrast;
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = '#ffffff';
        if (config.shape === 'round' || config.shape === 'seal') {
          ctx.beginPath();
          ctx.arc(0, 0, size * 0.28, 0, Math.PI * 2);
          ctx.stroke();
        } else if (config.shape === 'pill' || config.shape === 'slab') {
          const innerWidth = size * 0.6;
          const innerHeight = config.shape === 'pill' ? size * 0.24 : size * 0.34;
          ctx.beginPath();
          ctx.roundRect(-innerWidth / 2, -innerHeight / 2, innerWidth, innerHeight, innerHeight / 2);
          ctx.stroke();
        } else {
          drawPolygon(ctx, shapePoints(config.shape, size * 0.62));
          ctx.stroke();
        }
        ctx.restore();
        return PIXI.Texture.from(canvas);
      }

      function parseHostConfig(host) {
        const variant = host.dataset.variant || 'diamond';
        const base = BADGE_PRESETS[variant] || BADGE_PRESETS.diamond;
        let override = {};
        if (host.dataset.options) {
          try {
            override = JSON.parse(host.dataset.options);
          } catch (error) {
            console.warn('Invalid Pixi badge options', error);
          }
        }
        const merged = mergeConfig(base, override);
        merged.variant = variant;
        return merged;
      }

      function destroyHost(host) {
        if (host.__trkPixiApp) {
          try {
            host.__trkPixiApp.destroy(true, { children: true, texture: false, textureSource: false });
          } catch (_) {
          }
          host.__trkPixiApp = null;
        }
        host.dataset.rendered = 'false';
        host.innerHTML = '';
      }

            function buildSupremeHolyRay(layerDef, size, knobs) {
        const rayLen = size * 3.0;
        const uniformColor = layerDef.params.color ? toHexInt(layerDef.params.color) : toHexInt('#ffffff');
        const rayContainer = new PIXI.Container();

        const shaderFrag = 
          in vec2 vTextureCoord;
          out vec4 finalColor;

          uniform float uTime;
          uniform float uIntensity;

          vec3 getHolyColor(float p, float t_time) {
              vec3 c1 = vec3(1.0, 0.8, 0.4); 
              vec3 c2 = vec3(1.0, 0.5, 0.6); 
              vec3 c3 = vec3(0.7, 0.6, 1.0); 
              vec3 c4 = vec3(1.0, 1.0, 0.9); 
              
              float t = fract(p + t_time * 0.1);
              if(t < 0.33) return mix(c1, c2, t/0.33);
              if(t < 0.66) return mix(c2, c3, (t-0.33)/0.33);
              return mix(c3, c4, (t-0.66)/0.34);
          }

          void main() {
              vec2 uv = vTextureCoord;
              vec2 center = vec2(0.5, 0.5);
              
              vec2 distVec = uv - center;
              float dist = length(distVec) * 2.0; 
              float angle = atan(distVec.y, distVec.x);

              float t_time = uTime * 1.5;

              float rays = pow(abs(sin(angle * 6.0 + t_time * 0.8)), 4.0) * 0.7;
              rays += pow(abs(sin(angle * 12.0 - t_time * 0.4)), 8.0) * 0.5;
              rays += pow(abs(sin(angle * 3.0 + t_time * 0.2)), 2.0) * 0.3;
              
              float blossom = 0.15 / (dist + 0.1); 
              vec3 spectralBase = getHolyColor(angle / 6.28 + dist * 0.5, t_time);
              
              vec3 finalColorRGB = spectralBase * rays * blossom * (2.0 + uIntensity * 3.0);
              finalColorRGB += getHolyColor(t_time * 0.05, t_time) * blossom * (0.8 + uIntensity); 
              
              float alpha = smoothstep(1.0, 0.0, dist) * (rays + blossom);
              finalColor = vec4(finalColorRGB * alpha, alpha * 0.8);
          }
        ;

        const shaderVert = 
          in vec2 aPosition;
          out vec2 vTextureCoord;
          uniform vec4 uInputSize;
          uniform vec4 uOutputFrame;
          uniform vec4 uOutputTexture;
          uniform mat3 uProjectionMatrix;
          void main(void){
              vec2 position = aPosition * uOutputFrame.zw + uOutputFrame.xy;
              position.x = position.x * (2.0 / uOutputTexture.x) - 1.0;
              position.y = position.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.w;
              gl_Position = vec4(position, 0.0, 1.0);
              vTextureCoord = aPosition * (uOutputFrame.zw * uInputSize.zw);
          }
        ;

        try {
            const holyFilter = new PIXI.Filter({
                glProgram: PIXI.GlProgram.from({ vertex: shaderVert, fragment: shaderFrag }),
                resources: {
                    timeUniforms: {
                        uTime: { value: 0.0, type: 'f32' },
                        uIntensity: { value: 0.0, type: 'f32' }
                    }
                }
            });
            
            const dummySprite = new PIXI.Sprite(PIXI.Texture.WHITE);
            dummySprite.anchor.set(0.5);
            dummySprite.width = dummySprite.height = rayLen;
            dummySprite.filters = [holyFilter];
            dummySprite.blendMode = 'add';
            dummySprite.alpha = knobs.energy; // Additive layering governed by energy
            
            rayContainer.addChild(dummySprite);
            return {
               container: rayContainer,
               update: (delta, t, knobs) => {
                   holyFilter.resources.timeUniforms.uniforms.uTime = t * knobs.motion;
                   holyFilter.resources.timeUniforms.uniforms.uIntensity = knobs.energy;
                   dummySprite.alpha = knobs.energy;
               }
            };
        } catch (e) {
            console.warn('Holy Ray Shader Filter Fallback', e);
            const fallbackSprite = new PIXI.Container();
            return { container: fallbackSprite, update: ()=>{} };
        }
      }
function addOuterAura(root, config, size, knobs) {
        const outer = new PIXI.Sprite(makeRadialTexture(
          toRgba(config.colors.auraInner, 0.85 * knobs.energy),
          toRgba(config.colors.auraOuter, 0),
          320,
          toRgba(config.colors.edge, 0.22 * knobs.energy),
        ));
        outer.anchor.set(0.5);
        outer.width = size * config.metrics.outerAura * (1 + knobs.energy * 0.08);
        outer.height = outer.width;
        outer.blendMode = 'add';
        outer.alpha = 0.44 * knobs.energy;
        root.addChild(outer);

        const inner = new PIXI.Sprite(makeRadialTexture(
          toRgba(config.colors.coreStart, 0.96 * knobs.contrast),
          toRgba(config.colors.auraInner, 0),
          256,
          toRgba(config.colors.auraInner, 0.36 * knobs.energy),
        ));
        inner.anchor.set(0.5);
        inner.width = size * config.metrics.innerAura * (1 + knobs.energy * 0.05);
        inner.height = inner.width;
        inner.blendMode = 'add';
        inner.alpha = 0.58 * knobs.energy;
        root.addChild(inner);

        return { outer, inner };
      }

      function addRing(root, color, radius, alpha, width) {
        const ring = new PIXI.Graphics();
        ring.circle(0, 0, radius).stroke({ width, color: toHexInt(color), alpha });
        root.addChild(ring);
        return ring;
      }

      function addEffectLayer(root, config, size, knobs) {
        const beamTexture = makeBeamTexture(config.colors, size * 1.18, Math.max(18, size * 0.12));
        const layer = new PIXI.Container();
        const accent = new PIXI.Container();
        let ringA = null;
        let ringB = null;
        let orbitDots = [];
        let petals = [];
        let flares = [];

        function addBeams(count, widthFactor, heightFactor, alpha, phase = 0) {
          for (let i = 0; i < count; i++) {
            const beam = new PIXI.Sprite(beamTexture);
            beam.anchor.set(0.05, 0.5);
            beam.width = size * widthFactor;
            beam.height = size * heightFactor;
            beam.rotation = ((Math.PI * 2) / count) * i + phase;
            beam.alpha = alpha;
            beam.blendMode = 'add';
            layer.addChild(beam);
          }
        }

        switch (config.effect) {
          case 'cosmic':
            addBeams(12, 0.96, 0.12, 0.26 * knobs.energy);
            addBeams(6, 1.08, 0.08, 0.16 * knobs.energy, Math.PI / 6);
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.34, 2.4);
            ringB = addRing(root, config.colors.auraOuter, size * (config.metrics.ring + 0.06), 0.16, 1.8);
            for (let i = 0; i < 4; i++) {
              const flare = new PIXI.Graphics();
              flare.moveTo(size * 0.1, 0).lineTo(size * 0.28, 0).stroke({ width: 2.4, color: toHexInt(config.colors.edge), alpha: 0.26 });
              flare.rotation = i * (Math.PI / 2);
              flares.push(flare);
              accent.addChild(flare);
            }
            break;
          case 'flame':
            addBeams(10, 0.82, 0.18, 0.22 * knobs.energy, Math.PI / 10);
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.18, 2.0);
            for (let i = 0; i < 6; i++) {
              const petal = new PIXI.Graphics();
              petal.ellipse(size * 0.26, 0, size * 0.13, size * 0.055).fill({ color: toHexInt(config.colors.auraInner), alpha: 0.22 * knobs.energy });
              petal.rotation = (Math.PI * 2 * i) / 6;
              petal.blendMode = 'add';
              petals.push(petal);
              accent.addChild(petal);
            }
            break;
          case 'orbit':
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.28, 2.0);
            ringB = addRing(root, config.colors.auraOuter, size * (config.metrics.ring + 0.05), 0.14, 1.6);
            for (let i = 0; i < 4; i++) {
              const arc = new PIXI.Graphics();
              arc.arc(0, 0, size * (0.25 + i * 0.04), -0.3, 0.55).stroke({ width: 2, color: toHexInt(config.colors.edge), alpha: 0.18 });
              arc.rotation = i * (Math.PI / 2) + Math.PI / 10;
              accent.addChild(arc);
              flares.push(arc);
            }
            for (let i = 0; i < 3; i++) {
              const dot = new PIXI.Sprite(makeRadialTexture(toRgba(config.colors.edge, 1), toRgba(config.colors.auraOuter, 0), 80));
              dot.anchor.set(0.5);
              dot.width = dot.height = size * 0.08;
              dot.blendMode = 'add';
              dot.phase = (Math.PI * 2 * i) / 3;
              orbitDots.push(dot);
              accent.addChild(dot);
            }
            break;
          case 'rune':
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.22, 1.8);
            ringB = addRing(root, config.colors.auraOuter, size * (config.metrics.ring + 0.07), 0.12, 1.2);
            for (let i = 0; i < 6; i++) {
              const spoke = new PIXI.Graphics();
              spoke.moveTo(size * 0.12, 0).lineTo(size * 0.2, 0).stroke({ width: 2, color: toHexInt(config.colors.edge), alpha: 0.35 });
              spoke.rotation = (Math.PI * 2 * i) / 6;
              accent.addChild(spoke);
            }
            break;
          case 'nature':
            for (let i = 0; i < 8; i++) {
              const leaf = new PIXI.Graphics();
              leaf.ellipse(size * 0.3, 0, size * 0.08, size * 0.03).fill({ color: toHexInt(config.colors.auraInner), alpha: 0.22 * knobs.energy });
              leaf.rotation = (Math.PI * 2 * i) / 8;
              leaf.blendMode = 'add';
              accent.addChild(leaf);
            }
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.16, 1.6);
            break;
          case 'solar':
            addBeams(16, 0.72, 0.08, 0.18 * knobs.energy);
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.2, 1.8);
            break;
          case 'seam':
            for (let i = 0; i < 4; i++) {
              const seam = new PIXI.Graphics();
              seam.moveTo(size * 0.14, 0).lineTo(size * 0.28, 0).stroke({ width: 2.4, color: toHexInt(config.colors.edge), alpha: 0.3 });
              seam.rotation = Math.PI / 4 + (Math.PI / 2) * i;
              accent.addChild(seam);
            }
            break;
          case 'metal':
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.14, 1.4);
            break;
          case 'wave':
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.18, 1.8);
            ringB = addRing(root, config.colors.auraInner, size * (config.metrics.ring + 0.08), 0.12, 1.2);
            break;
          case 'fog':
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.08, 1.2);
            break;
          case 'collapse':
            for (let i = 0; i < 5; i++) {
              const fragment = new PIXI.Graphics();
              fragment.poly([0, 0, size * 0.06, -size * 0.02, size * 0.11, size * 0.04]).fill({ color: toHexInt(config.colors.auraInner), alpha: 0.26 });
              fragment.rotation = (Math.PI * 2 * i) / 5;
              fragment.x = Math.cos(fragment.rotation) * size * 0.28;
              fragment.y = Math.sin(fragment.rotation) * size * 0.28;
              accent.addChild(fragment);
            }
            break;
          case 'shadow':
            ringA = addRing(root, config.colors.edge, size * config.metrics.ring, 0.06, 1.2);
            break;
          default:
            break;
        }

        root.addChild(layer);
        root.addChild(accent);
        return { layer, accent, ringA, ringB, orbitDots, petals, flares, effect: config.effect };
      }

      function addCore(root, config, size, score, knobs) {
        const core = new PIXI.Sprite(drawCoreTexture(config, 256, knobs.contrast));
        core.anchor.set(0.5);
        core.width = size * config.metrics.coreScale;
        core.height = core.width;
        root.addChild(core);

        const glare = new PIXI.Graphics();
        glare.ellipse(0, -size * 0.11, size * 0.12, size * 0.04).fill({ color: 0xffffff, alpha: 0.22 * knobs.contrast });
        glare.blendMode = 'add';
        root.addChild(glare);

        const scoreText = new PIXI.Text({
          text: score,
          style: {
            fontFamily: 'Segoe UI, Arial, sans-serif',
            fontSize: Math.max(20, size * 0.16),
            fontWeight: '900',
            fill: config.colors.text,
            letterSpacing: 1.1,
            dropShadow: {
              alpha: 0.72,
              angle: Math.PI / 2,
              blur: 8,
              color: config.colors.shadow,
              distance: 4,
            },
          },
        });
        scoreText.anchor.set(0.5);
        root.addChild(scoreText);
        return { core, glare, scoreText };
      }

      function addParticles(root, config, size, knobs) {
        const density = clamp(knobs.particles, 0, 2);
        const count = Math.round((6 + size * 0.04) * density);
        const particles = [];
        if (!count) return particles;
        const texture = makeRadialTexture(toRgba(config.colors.coreStart, 1), toRgba(config.colors.auraOuter, 0), 96);
        for (let i = 0; i < count; i++) {
          const particle = new PIXI.Sprite(texture);
          particle.anchor.set(0.5);
          particle.width = particle.height = 4 + Math.random() * Math.max(6, size * 0.05);
          particle.blendMode = 'add';
          particle.alpha = 0.18 + Math.random() * 0.34;
          particle.phase = Math.random() * Math.PI * 2;
          particle.radius = size * (0.22 + Math.random() * 0.24);
          particle.speed = 0.005 + Math.random() * 0.018;
          particle.drift = 6 + Math.random() * 12;
          root.addChildAt(particle, 1);
          particles.push(particle);
        }
        return particles;
      }

      async function renderHost(host) {
        if (!window.PIXI) return;
        destroyHost(host);

        const score = String(host.dataset.score || '99');
        const config = parseHostConfig(host);
        const knobs = {
          energy: clamp(Number(config.controls?.energy ?? config.defaults.energy ?? 1), 0, 2),
          motion: clamp(Number(config.controls?.motion ?? config.defaults.motion ?? 1), 0, 2),
          particles: clamp(Number(config.controls?.particles ?? config.defaults.particles ?? 1), 0, 2),
          contrast: clamp(Number(config.controls?.contrast ?? config.defaults.contrast ?? 1), 0.7, 1.5),
        };

        const app = new PIXI.Application();
        await app.init({ resizeTo: host, backgroundAlpha: 0, antialias: true });
        const fallback = host.closest('.trk-pixi-fallback-wrap')?.querySelector('.trk-pixi-fallback');
        if (fallback) {
          fallback.remove();
        }
        host.__trkPixiApp = app;
        app.canvas.classList.add('trk-pixi-canvas');
        host.appendChild(app.canvas);

        const root = new PIXI.Container();
        const size = Math.min(host.clientWidth || 220, host.clientHeight || 220);
        root.x = (host.clientWidth || size) / 2;
        root.y = (host.clientHeight || size) / 2;
        app.stage.addChild(root);

        
        const layers = config.layers || [
            { type: 'aura', params: {} },
            { type: 'effect', params: { effect: config.effect } },
            { type: 'shape', params: { shape: config.shape } },
            { type: 'particles', params: {} }
        ];

        const activeLayerUpdates = [];

        layers.forEach(layerDef => {
            if (layerDef.type === 'shader_aura' && layerDef.params.shader === 'supreme_holy_ray') {
                const r = buildSupremeHolyRay(layerDef, size, knobs);
                root.addChild(r.container);
                activeLayerUpdates.push(r.update);
            }
            else if (layerDef.type === 'aura') {
                const a = addOuterAura(root, config, size, knobs);
                activeLayerUpdates.push((delta, t, updatedKnobs) => {
                   const pulse = Math.sin(t * (1.4 + updatedKnobs.motion * 1.6));
                   const breathe = Math.sin(t * (0.7 + updatedKnobs.motion));
                   a.outer.scale.set(1 + pulse * 0.045 * updatedKnobs.energy);
                   a.inner.scale.set(1 + breathe * 0.038 * updatedKnobs.energy);
                   a.outer.alpha = 0.24 + updatedKnobs.energy * 0.22 + pulse * 0.06;
                   a.inner.alpha = 0.26 + updatedKnobs.energy * 0.3 + breathe * 0.05;
                });
            }
            else if (layerDef.type === 'effect') {
                // To adapt dynamically selected aura colors if custom:
                if (layerDef.params.colorEdge) {
                    config.colors.edge = layerDef.params.colorEdge;
                    config.colors.auraInner = layerDef.params.colorEdge;
                    config.colors.auraOuter = layerDef.params.colorEdge;
                }
                config.effect = layerDef.params.effect || config.effect;
                const fx = addEffectLayer(root, config, size, knobs);
                activeLayerUpdates.push((delta, t, updatedKnobs) => {
                   const pulse = Math.sin(t * (1.4 + updatedKnobs.motion * 1.6));
                   const breathe = Math.sin(t * (0.7 + updatedKnobs.motion));
                   if (fx.layer) { fx.layer.rotation += (0.001 + updatedKnobs.motion * 0.0018) * delta; }
                   if (fx.accent) { fx.accent.rotation -= (0.0004 + updatedKnobs.motion * 0.001) * delta; }
                   if (fx.ringA) { fx.ringA.alpha = Math.max(0.02, 0.12 + updatedKnobs.energy * 0.18 + breathe * 0.04); }
                   if (fx.ringB) { fx.ringB.alpha = Math.max(0.02, 0.06 + updatedKnobs.energy * 0.1 + pulse * 0.03); fx.ringB.rotation += 0.0009 * delta * updatedKnobs.motion; }
                   fx.orbitDots.forEach((dot, index) => {
                        const orbit = t * (0.9 + updatedKnobs.motion * 1.1) + dot.phase;
                        dot.x = Math.cos(orbit) * size * 0.33;
                        dot.y = Math.sin(orbit * 1.08) * size * 0.26;
                        dot.alpha = 0.22 + ((Math.sin(orbit + index) + 1) / 2) * 0.34;
                   });
                   fx.petals.forEach((petal, index) => {
                        const lick = Math.sin(t * (2.6 + updatedKnobs.motion * 1.8) + index * 0.7);
                        petal.scale.set(1 + lick * 0.12, 1 + Math.max(0, lick) * 0.34);
                        petal.alpha = 0.14 + ((lick + 1) / 2) * 0.22 * updatedKnobs.energy;
                   });
                   fx.flares.forEach((flare, index) => {
                        const shimmer = Math.sin(t * (1.3 + updatedKnobs.motion) + index * 0.8);
                        flare.alpha = Math.max(0.06, 0.16 + shimmer * 0.08);
                   });
                   if (fx.effect === 'flame') {
                       if (fx.layer) { fx.layer.rotation += Math.sin(t * 2.8) * 0.0008 * delta; fx.layer.scale.y = 1 + Math.max(0, pulse) * 0.08; }
                       if (fx.accent) { fx.accent.y = -Math.max(0, breathe) * size * 0.014; }
                   } else if (fx.effect === 'orbit') {
                       if (fx.layer) { fx.layer.rotation += 0.0002 * delta; }
                       if (fx.accent) { fx.accent.rotation += 0.0005 * delta * updatedKnobs.motion; }
                   } else if (fx.effect === 'cosmic') {
                       if (fx.ringA) { fx.ringA.scale.set(1 + Math.max(0, pulse * 0.025)); }
                       if (fx.ringB) { fx.ringB.scale.set(1 + Math.max(0, breathe * 0.04)); }
                   }
                });
            }
            else if (layerDef.type === 'shape') {
                if (layerDef.params.colorStart) config.colors.coreStart = layerDef.params.colorStart;
                if (layerDef.params.colorEnd) config.colors.coreEnd = layerDef.params.colorEnd;
                if (layerDef.params.colorEdge) config.colors.edge = layerDef.params.colorEdge;
                config.shape = layerDef.params.shape || config.shape;
                const c = addCore(root, config, size, score, knobs);
                activeLayerUpdates.push((delta, t, updatedKnobs) => {
                   const pulse = Math.sin(t * (1.4 + updatedKnobs.motion * 1.6));
                   c.core.scale.set(1 + pulse * 0.012 * updatedKnobs.energy);
                   c.scoreText.scale.set(1 + pulse * 0.008 * updatedKnobs.energy);
                   c.glare.alpha = Math.max(0, 0.14 + (pulse + 1) * 0.05 * updatedKnobs.contrast);
                });
            }
            else if (layerDef.type === 'particles') {
                const pts = addParticles(root, config, size, knobs);
                activeLayerUpdates.push((delta, t, updatedKnobs) => {
                   pts.forEach((particle, index) => {
                        const orbit = particle.phase + t * (0.8 + updatedKnobs.motion * 1.2 + particle.speed * 12);
                        particle.x = Math.cos(orbit) * particle.radius;
                        particle.y = Math.sin(orbit * 1.2 + index) * particle.drift - size * 0.06;
                        particle.alpha = 0.12 + ((Math.sin(orbit * 2 + index) + 1) / 2) * 0.38 * Math.max(0.2, updatedKnobs.particles);
                   });
                });
            }
        });

        host.dataset.rendered = 'true';
        let elapsed = 0;
        app.ticker.add((ticker) => {
          elapsed += ticker.deltaTime;
          const t = elapsed / 60;
          activeLayerUpdates.forEach(updateFn => updateFn(ticker.deltaTime, t, knobs));
        });
      }

      window.__destroyTrackerPixiBadge = destroyHost;
      window.__renderTrackerPixiBadges = async function(root = document) {
        const scope = root && root.querySelectorAll ? root : document;
        const hosts = Array.from(scope.querySelectorAll('.trk-pixi-badge'));
        for (const host of hosts) {
          try {
            await renderHost(host);
          } catch (error) {
            console.error('Pixi badge render failed', error);
            host.innerHTML = `<span style="color:red;font-size:10px;line-height:1;word-break:break-all">${error.message||error}</span>`;
          }
        }
      };

      window.addEventListener('load', () => {
        window.__renderTrackerPixiBadges();
      }, { once: true });
    })();
    </script>
    '''


def pixi_badge_host(
    score: int | str,
    *,
    size: int = 230,
    variant: str = 'diamond',
    host_id: str | None = None,
    extra_classes: str = '',
    options: dict | None = None,
  fallback_html: str | None = None,
) -> str:
    host_id = host_id or f'trk-pixi-badge-{uuid4().hex}'
    classes = 'trk-pixi-badge'
    if extra_classes:
        classes += f' {extra_classes}'
    options_attr = ''
    if options:
        options_json = html.escape(json.dumps(options, separators=(',', ':')))
        options_attr = f' data-options="{options_json}"'
    host_html = (
      f'<div id="{html.escape(host_id)}" '
      f'class="{html.escape(classes)}" '
      f'data-score="{html.escape(str(score))}" '
      f'data-variant="{html.escape(variant)}"'
      f'{options_attr} '
      f'style="width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;position:relative;z-index:1;"></div>'
    )
    if not fallback_html:
      return host_html
    return (
      f'<div class="trk-pixi-fallback-wrap" '
      f'style="width:{size}px;height:{size}px;display:flex;align-items:center;justify-content:center;position:relative;">'
      f'<div class="trk-pixi-fallback" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;z-index:0;">{fallback_html}</div>'
      f'{host_html}'
      f'</div>'
    )