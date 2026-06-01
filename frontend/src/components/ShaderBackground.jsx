import { MeshGradient, PulsingBorder } from "@paper-design/shaders-react";

export default function ShaderBackground({ showCornerDecor = true }) {
  return (
    <>
      {/* SVG filter defs — used by glass-effect on overlays */}
      <svg className="absolute w-0 h-0 overflow-hidden" aria-hidden="true">
        <defs>
          <filter id="glass-effect" x="-50%" y="-50%" width="200%" height="200%">
            <feTurbulence baseFrequency="0.005" numOctaves="1" result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="0.3" />
            <feColorMatrix
              type="matrix"
              values="1 0 0 0 0.02
                      0 1 0 0 0.02
                      0 0 1 0 0.05
                      0 0 0 0.9 0"
            />
          </filter>
        </defs>
      </svg>

      {/* Primary mesh gradient */}
      <MeshGradient
        className="fixed inset-0 w-full h-full"
        style={{ zIndex: -2 }}
        colors={["#000000", "#06b6d4", "#0891b2", "#164e63", "#f97316"]}
        speed={0.3}
        backgroundColor="#000000"
      />

      {/* Wireframe overlay for depth */}
      <MeshGradient
        className="fixed inset-0 w-full h-full opacity-50"
        style={{ zIndex: -1 }}
        colors={["#000000", "#ffffff", "#06b6d4", "#f97316"]}
        speed={0.2}
        wireframe={true}
        backgroundColor="transparent"
      />

      {/* Corner pulsing orb */}
      {showCornerDecor && (
        <div className="fixed bottom-6 right-6 z-10 pointer-events-none">
          <PulsingBorder
            colors={["#06b6d4", "#0891b2", "#f97316", "#00FF88", "#FFD700", "#FF6B35", "#ffffff"]}
            colorBack="#00000000"
            speed={1.5}
            roundness={1}
            thickness={0.1}
            softness={0.2}
            intensity={5}
            spotsPerColor={5}
            spotSize={0.1}
            pulse={0.1}
            smoke={0.5}
            smokeSize={4}
            scale={0.65}
            rotation={0}
            style={{ width: "60px", height: "60px", borderRadius: "50%" }}
          />
        </div>
      )}
    </>
  );
}
