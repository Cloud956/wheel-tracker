import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import { existsSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 3000;

// Check if dist directory exists
const distPath = path.join(__dirname, 'dist');
if (!existsSync(distPath)) {
  console.error('ERROR: dist directory does not exist!');
  console.error('Please run "npm run build" first.');
  process.exit(1);
}

// Serve static files from the dist directory (built React app)
app.use(express.static(distPath));

// API proxy for development/production
const API_BASE = process.env.API_BASE || 'http://localhost:8000';
app.use('/api', async (req, res) => {
  try {
    const response = await fetch(`${API_BASE}${req.path}`);
    const data = await response.json();
    res.json(data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Fallback to index.html for client-side routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'dist', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});


