import React from "react";

type GlobeProps = {
  className?: string;
  fullScreen?: boolean;
  size?: number;
};

const Globe: React.FC<GlobeProps> = ({className = "", fullScreen = true, size = 250}) => {
  const globe = (
    <div
      className={`relative rounded-full overflow-hidden shadow-[0_0_26px_rgba(212,175,55,0.22),-5px_0_10px_#e7e7e7_inset,15px_2px_25px_#000_inset,-24px_-2px_34px_#d4af3799_inset,250px_0_44px_#00000066_inset,150px_0_38px_#000000aa_inset] ${className}`}
      style={{
        width: size,
        height: size,
        backgroundImage: "url('https://pub-940ccf6255b54fa799a9b01050e6c227.r2.dev/globe.jpeg')",
        backgroundSize: "cover",
        backgroundPosition: "left",
        animation: "earthRotate 30s linear infinite",
      }}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_68%_35%,rgba(245,197,87,0.18),transparent_31%),linear-gradient(90deg,rgba(212,175,55,0.16),transparent_38%,rgba(231,231,231,0.08))] mix-blend-screen" />
      {/* Stars */}
      <div
        className="absolute left-[-20px] w-1 h-1 bg-[#f5c557] rounded-full"
        style={{ animation: "twinkling 3s infinite" }}
      />
      <div
        className="absolute left-[-40px] top-[30px] w-1 h-1 bg-[#e7e7e7] rounded-full"
        style={{ animation: "twinkling-slow 2s infinite" }}
      />
      <div
        className="absolute left-[350px] top-[90px] w-1 h-1 bg-[#d4af37] rounded-full"
        style={{ animation: "twinkling-long 4s infinite" }}
      />
      <div
        className="absolute left-[200px] top-[290px] w-1 h-1 bg-[#f5c557] rounded-full"
        style={{ animation: "twinkling 3s infinite" }}
      />
      <div
        className="absolute left-[50px] top-[270px] w-1 h-1 bg-[#e7e7e7] rounded-full"
        style={{ animation: "twinkling-fast 1.5s infinite" }}
      />
      <div
        className="absolute left-[250px] top-[-50px] w-1 h-1 bg-[#d4af37] rounded-full"
        style={{ animation: "twinkling-long 4s infinite" }}
      />
      <div
        className="absolute left-[290px] top-[60px] w-1 h-1 bg-[#f5c557] rounded-full"
        style={{ animation: "twinkling-slow 2s infinite" }}
      />
    </div>
  );

  return (
    <>
      <style>
        {`
          @keyframes earthRotate {
            0% { background-position: 0 0; }
            100% { background-position: 400px 0; }
          }
          @keyframes twinkling { 0%,100% { opacity:0.1; } 50% { opacity:1; } }
          @keyframes twinkling-slow { 0%,100% { opacity:0.1; } 50% { opacity:1; } }
          @keyframes twinkling-long { 0%,100% { opacity:0.1; } 50% { opacity:1; } }
          @keyframes twinkling-fast { 0%,100% { opacity:0.1; } 50% { opacity:1; } }
        `}
      </style>
      {fullScreen ? <div className="flex items-center justify-center h-screen">{globe}</div> : globe}
    </>
  );
};

export default Globe;
