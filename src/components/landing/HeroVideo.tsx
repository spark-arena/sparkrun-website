import { useEffect, useRef } from 'react';
import 'asciinema-player/dist/bundle/asciinema-player.css';

export default function HeroVideo() {
  const playerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!playerRef.current) return;
    let player: { dispose?: () => void } | null = null;
    let cancelled = false;
    import('asciinema-player').then((AsciinemaPlayer) => {
      if (cancelled || !playerRef.current) return;
      player = AsciinemaPlayer.create('/sparkrun-demo.cast', playerRef.current, {
        autoPlay: true,
        loop: true,
        preload: true,
        controls: false,
        speed: 2,
        idleTimeLimit: 1.5,
        fit: 'width',
        theme: 'asciinema',
        terminalFontSize: 'small',
      });
    });
    return () => {
      cancelled = true;
      player?.dispose?.();
    };
  }, []);

  return (
    <>
      <div className="hero-video-background not-content"></div>
      <div className="hero-terminal-container not-content">
        <div className="terminal-header">
          <span className="terminal-title">sparkrun</span>
        </div>
        <div className="hero-video-wrapper">
          <div ref={playerRef} className="hero-asciinema" />
        </div>
      </div>
    </>
  );
}
