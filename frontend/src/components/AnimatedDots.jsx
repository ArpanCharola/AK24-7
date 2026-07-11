import { useEffect, useRef } from "react";

export default function AnimatedDots({
  dotsNum = 60,
  dotRadius = 10,
  dotSpacing = 0,
  speedRange = [1, 4],
  backgroundColor = "transparent",
  opacity = 1,
  blendMode = "normal",
  fullScreen = true,
  className = "",
  colors = [
    ["red",    255,  69,  58],
    ["blue",     0, 122, 255],
    ["indigo",  88,  86, 214],
    ["purple", 175,  82, 222],
    ["pink",   255,  45,  85],
  ],
}) {
  const canvasRef = useRef(null);
  const dotsRef   = useRef([]);
  const animRef   = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx    = canvas.getContext("2d");
    const TWO_PI = 2 * Math.PI;
    let width    = fullScreen ? window.innerWidth  : canvas.offsetWidth;
    let height   = fullScreen ? window.innerHeight : canvas.offsetHeight;

    class Dot {
      constructor() {
        this.velocity    = Math.random() * height; // stagger so they don't all start at top
        this.radius      = dotRadius;
        this.ranVelocity = Math.random() * (speedRange[1] - speedRange[0]) + speedRange[0];
        this.ranColor    = Math.round(Math.random() * (colors.length - 1));
        this.x           = Math.random() * width;  // scatter across full width
        this.y           = -this.radius;
      }

      draw() {
        this.velocity += this.ranVelocity;
        const colorIncrement = 255 - Math.round(this.velocity * (255 / (height + this.radius)));

        ctx.fillStyle             = this._color(colors[this.ranColor], colorIncrement);
        ctx.globalAlpha           = opacity;
        ctx.globalCompositeOperation = blendMode;

        if (this.velocity >= height + this.radius) {
          this.velocity    = 0;
          this.x           = Math.random() * width; // new random column on reset
          this.ranColor    = Math.round(Math.random() * (colors.length - 1));
          this.ranVelocity = Math.random() * (speedRange[1] - speedRange[0]) + speedRange[0];
        }

        this.y = -this.radius + this.velocity;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, TWO_PI, false);
        ctx.fill();
      }

      _color([type, r, g, b], inc) {
        if (type === "red")   r = inc;
        else if (type === "green") g = inc;
        else if (type === "blue")  b = inc;
        return `rgba(${r},${g},${b},1)`;
      }
    }

    const createDots = () => {
      dotsRef.current = [];
      for (let i = 0; i < dotsNum; i++) dotsRef.current.push(new Dot());
    };

    const resize = () => {
      width  = fullScreen ? window.innerWidth  : canvas.offsetWidth;
      height = fullScreen ? window.innerHeight : canvas.offsetHeight;
      canvas.width  = width;
      canvas.height = height;
      createDots();
    };

    const draw = () => {
      ctx.fillStyle = backgroundColor;
      ctx.fillRect(0, 0, width, height);
      for (const dot of dotsRef.current) dot.draw();
      animRef.current = requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [dotsNum, dotRadius, dotSpacing, speedRange, backgroundColor, opacity, blendMode, fullScreen, colors]);

  return (
    <div className={`${fullScreen ? "fixed inset-0" : "relative"} ${className}`}>
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}
