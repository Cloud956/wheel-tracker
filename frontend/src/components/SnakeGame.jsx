import React, { useRef, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './SnakeGame.css';

// MAG7 stocks with brand colors and ticker symbols
const MAG7 = [
  { ticker: 'AAPL',  color: '#A2AAAD', bg: '#1d1d1f', icon: '' },
  { ticker: 'MSFT',  color: '#00a4ef', bg: '#1a1a2e', icon: '⊞' },
  { ticker: 'GOOGL', color: '#4285F4', bg: '#1a2a1a', icon: 'G' },
  { ticker: 'AMZN',  color: '#FF9900', bg: '#1a1a10', icon: '→' },
  { ticker: 'NVDA',  color: '#76B900', bg: '#1a2a1a', icon: '▲' },
  { ticker: 'META',  color: '#0668E1', bg: '#0a1a2e', icon: '∞' },
  { ticker: 'TSLA',  color: '#cc0000', bg: '#1a0a0a', icon: 'T' },
];

const CELL_SIZE = 22;
const GRID_W = 36;
const GRID_H = 28;
const CANVAS_W = GRID_W * CELL_SIZE;
const CANVAS_H = GRID_H * CELL_SIZE;

const INITIAL_SPEED = 120;  // ms per tick
const SPEED_INCREASE = 2;   // ms faster per food eaten
const MIN_SPEED = 50;

function randomFoodPos(snake) {
  const occupied = new Set(snake.map(s => `${s.x},${s.y}`));
  let pos;
  do {
    pos = {
      x: Math.floor(Math.random() * GRID_W),
      y: Math.floor(Math.random() * GRID_H),
    };
  } while (occupied.has(`${pos.x},${pos.y}`));
  return pos;
}

function randomStock() {
  return MAG7[Math.floor(Math.random() * MAG7.length)];
}

function SnakeGame() {
  const canvasRef = useRef(null);
  const navigate = useNavigate();

  // Game state refs (not React state — to avoid re-renders on every tick)
  const snakeRef = useRef([{ x: 18, y: 14 }]);
  const dirRef = useRef({ x: 1, y: 0 });
  const nextDirRef = useRef({ x: 1, y: 0 });
  const foodRef = useRef({ ...randomFoodPos([{ x: 18, y: 14 }]), stock: randomStock() });
  const scoreRef = useRef(0);
  const speedRef = useRef(INITIAL_SPEED);
  const loopRef = useRef(null);
  const collectedRef = useRef({});  // { ticker: count }

  // React state for UI overlays
  const [gameState, setGameState] = useState('idle');  // 'idle' | 'playing' | 'dead'
  const [score, setScore] = useState(0);
  const [highScore, setHighScore] = useState(() => {
    return parseInt(localStorage.getItem('snakeHighScore') || '0', 10);
  });
  const [collected, setCollected] = useState({});

  // Leaderboard state
  const [leaderboard, setLeaderboard] = useState([]);
  const [playerName, setPlayerName] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const API_BASE = '/api';

  // Fetch leaderboard on mount
  useEffect(() => {
    fetchLeaderboard();
  }, []);

  const fetchLeaderboard = async () => {
    try {
      const resp = await fetch(`${API_BASE}/snake/highscores`);
      if (resp.ok) {
        const data = await resp.json();
        setLeaderboard(data);
      }
    } catch (e) {
      console.error('Failed to fetch leaderboard:', e);
    }
  };

  const submitHighscore = async () => {
    if (!playerName.trim() || submitting) return;
    setSubmitting(true);
    try {
      const resp = await fetch(`${API_BASE}/snake/highscore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: playerName.trim(),
          score: score,
          collected: collected,
        }),
      });
      if (resp.ok) {
        setSubmitted(true);
        fetchLeaderboard();  // Refresh leaderboard
      }
    } catch (e) {
      console.error('Failed to submit highscore:', e);
    } finally {
      setSubmitting(false);
    }
  };

  const draw = useCallback(() => {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;

    // Background
    ctx.fillStyle = '#0f0f0f';
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    // Snake
    const snake = snakeRef.current;
    snake.forEach((seg, i) => {
      const isHead = i === 0;
      const brightness = Math.max(40, 100 - i * 3);
      ctx.fillStyle = isHead ? '#00ff88' : `hsl(153, 100%, ${brightness}%)`;
      ctx.shadowColor = isHead ? '#00ff88' : 'transparent';
      ctx.shadowBlur = isHead ? 8 : 0;

      const padding = isHead ? 1 : 2;
      ctx.beginPath();
      ctx.roundRect(
        seg.x * CELL_SIZE + padding,
        seg.y * CELL_SIZE + padding,
        CELL_SIZE - padding * 2,
        CELL_SIZE - padding * 2,
        isHead ? 5 : 3
      );
      ctx.fill();
      ctx.shadowBlur = 0;
    });

    // Food (stock icon)
    const food = foodRef.current;
    const stock = food.stock;
    const fx = food.x * CELL_SIZE;
    const fy = food.y * CELL_SIZE;

    // Glow
    ctx.shadowColor = stock.color;
    ctx.shadowBlur = 12;
    ctx.fillStyle = stock.bg;
    ctx.beginPath();
    ctx.roundRect(fx + 2, fy + 2, CELL_SIZE - 4, CELL_SIZE - 4, 4);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Border
    ctx.strokeStyle = stock.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(fx + 2, fy + 2, CELL_SIZE - 4, CELL_SIZE - 4, 4);
    ctx.stroke();

    // Ticker text
    ctx.fillStyle = stock.color;
    ctx.font = 'bold 8px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(stock.ticker.slice(0, 4), fx + CELL_SIZE / 2, fy + CELL_SIZE / 2);
  }, []);

  const tick = useCallback(() => {
    const snake = snakeRef.current;
    dirRef.current = nextDirRef.current;
    const dir = dirRef.current;

    const head = {
      x: (snake[0].x + dir.x + GRID_W) % GRID_W,
      y: (snake[0].y + dir.y + GRID_H) % GRID_H,
    };

    // Self-collision
    if (snake.some(s => s.x === head.x && s.y === head.y)) {
      clearInterval(loopRef.current);
      setGameState('dead');

      // Update high score
      if (scoreRef.current > highScore) {
        const newHigh = scoreRef.current;
        setHighScore(newHigh);
        localStorage.setItem('snakeHighScore', String(newHigh));
      }
      setCollected({ ...collectedRef.current });
      return;
    }

    const newSnake = [head, ...snake];
    const food = foodRef.current;

    // Eat food?
    if (head.x === food.x && head.y === food.y) {
      scoreRef.current += 10;
      setScore(scoreRef.current);

      // Track collected stock
      const t = food.stock.ticker;
      collectedRef.current[t] = (collectedRef.current[t] || 0) + 1;

      // Speed up
      speedRef.current = Math.max(MIN_SPEED, speedRef.current - SPEED_INCREASE);
      clearInterval(loopRef.current);
      loopRef.current = setInterval(tick, speedRef.current);

      // New food
      foodRef.current = { ...randomFoodPos(newSnake), stock: randomStock() };
    } else {
      newSnake.pop();
    }

    snakeRef.current = newSnake;
    draw();
  }, [draw, highScore]);

  const startGame = useCallback(() => {
    snakeRef.current = [{ x: 18, y: 14 }];
    dirRef.current = { x: 1, y: 0 };
    nextDirRef.current = { x: 1, y: 0 };
    foodRef.current = { ...randomFoodPos([{ x: 18, y: 14 }]), stock: randomStock() };
    scoreRef.current = 0;
    speedRef.current = INITIAL_SPEED;
    collectedRef.current = {};
    setScore(0);
    setCollected({});
    setSubmitted(false);
    setPlayerName('');
    setGameState('playing');

    clearInterval(loopRef.current);
    loopRef.current = setInterval(tick, speedRef.current);
    draw();
  }, [tick, draw]);

  // Keyboard controls
  useEffect(() => {
    const handleKey = (e) => {
      const dir = dirRef.current;
      switch (e.key) {
        case 'ArrowUp':
        case 'w':
        case 'W':
          e.preventDefault();
          if (dir.y !== 1) nextDirRef.current = { x: 0, y: -1 };
          break;
        case 'ArrowDown':
        case 's':
        case 'S':
          e.preventDefault();
          if (dir.y !== -1) nextDirRef.current = { x: 0, y: 1 };
          break;
        case 'ArrowLeft':
        case 'a':
        case 'A':
          e.preventDefault();
          if (dir.x !== 1) nextDirRef.current = { x: -1, y: 0 };
          break;
        case 'ArrowRight':
        case 'd':
        case 'D':
          e.preventDefault();
          if (dir.x !== -1) nextDirRef.current = { x: 1, y: 0 };
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, []);

  // Cleanup interval on unmount only
  useEffect(() => {
    return () => clearInterval(loopRef.current);
  }, []);

  // Initial draw
  useEffect(() => {
    draw();
  }, [draw]);

  return (
    <div className="snake-page">
      <div className="snake-header">
        <h1>🐍 MAG7 Snake</h1>
        <button className="back-btn" onClick={() => navigate('/dashboard')}>
          ← Back to Dashboard
        </button>
      </div>

      <div className="snake-scoreboard">
        <span>Score: <span className="score-value">{score}</span></span>
        <span>High: <span className="highscore-value">{highScore}</span></span>
      </div>

      <div className="snake-main-layout">
        <div className="snake-canvas-wrapper">
          <canvas
            ref={canvasRef}
            width={CANVAS_W}
            height={CANVAS_H}
          />

          {gameState === 'idle' && (
            <div className="snake-overlay">
              <h2 style={{ color: '#00ff88' }}>🐍 MAG7 Snake</h2>
              <p style={{ color: '#888', marginBottom: '1.5rem' }}>
                Collect the Magnificent 7 stocks!
              </p>
              <button className="snake-start-btn" onClick={startGame}>
                Start Game
              </button>
            </div>
          )}

          {gameState === 'dead' && (
            <div className="snake-overlay">
              <h2>Game Over!</h2>
              <p className="final-score">Score: {score}</p>

              {Object.keys(collected).length > 0 && (
                <div className="collected-stocks">
                  {Object.entries(collected)
                    .sort((a, b) => b[1] - a[1])
                    .map(([ticker, count]) => (
                      <span key={ticker} className="stock-badge">
                        {ticker}: <span className="count">×{count}</span>
                      </span>
                    ))}
                </div>
              )}

              {!submitted ? (
                <div className="highscore-form">
                  <input
                    type="text"
                    className="name-input"
                    placeholder="Your name..."
                    value={playerName}
                    onChange={(e) => setPlayerName(e.target.value)}
                    maxLength={20}
                    onKeyDown={(e) => { if (e.key === 'Enter') submitHighscore(); }}
                  />
                  <button
                    className="snake-restart-btn"
                    onClick={submitHighscore}
                    disabled={!playerName.trim() || submitting}
                    style={{ fontSize: '0.9rem', padding: '0.5rem 1.2rem' }}
                  >
                    {submitting ? 'Saving...' : 'Save Score'}
                  </button>
                </div>
              ) : (
                <p style={{ color: '#00ff88', marginBottom: '1rem' }}>✓ Score saved!</p>
              )}

              <button className="snake-restart-btn" onClick={startGame}>
                Play Again
              </button>
            </div>
          )}
        </div>

        <div className="snake-leaderboard">
          <h3>🏆 Leaderboard</h3>
          {leaderboard.length === 0 ? (
            <p className="lb-empty">No scores yet. Be the first!</p>
          ) : (
            <ol className="lb-list">
              {leaderboard.map((entry, i) => (
                <li key={i} className={`lb-entry ${i < 3 ? 'lb-top' : ''}`}>
                  <span className="lb-rank">{i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i + 1}.`}</span>
                  <span className="lb-name">{entry.name}</span>
                  <span className="lb-score">{entry.score}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      <p className="snake-controls-hint">
        Use <kbd>↑</kbd> <kbd>↓</kbd> <kbd>←</kbd> <kbd>→</kbd> or <kbd>W</kbd> <kbd>A</kbd> <kbd>S</kbd> <kbd>D</kbd> to move
      </p>
    </div>
  );
}

export default SnakeGame;
