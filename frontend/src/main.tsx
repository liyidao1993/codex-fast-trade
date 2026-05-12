import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Trade } from './pages/Trade';
import './styles.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Trade />
  </StrictMode>
);

