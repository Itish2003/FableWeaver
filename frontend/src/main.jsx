import React from 'react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class GlobalErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ error, errorInfo });
    console.error("Critical Global Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundColor: '#000',
          color: '#ff5555',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          fontFamily: 'monospace',
          zIndex: 9999
        }}>
          <h1 style={{ fontSize: '2rem', marginBottom: '1rem' }}>Application Crash</h1>
          <div style={{ maxWidth: '800px', width: '100%', overflow: 'auto', border: '1px solid #333', padding: '1rem' }}>
             <h3 style={{ borderBottom: '1px solid #333', paddingBottom: '0.5rem' }}>Error:</h3>
             <pre style={{ whiteSpace: 'pre-wrap' }}>{this.state.error && this.state.error.toString()}</pre>
             <h3 style={{ marginTop: '1rem', borderBottom: '1px solid #333', paddingBottom: '0.5rem' }}>Stack:</h3>
             <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.8rem', opacity: 0.7 }}>
               {this.state.errorInfo && this.state.errorInfo.componentStack}
             </pre>
          </div>
        </div>
      );
    }
    return this.props.children; 
  }
}

createRoot(document.getElementById('root')).render(
  <GlobalErrorBoundary>
    <StrictMode>
      <App />
    </StrictMode>
  </GlobalErrorBoundary>,
)
