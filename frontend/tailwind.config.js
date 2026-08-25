/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Neural Clarity palette
        bg: {
          base: '#0A0E1A',
          surface: '#111827',
          elevated: '#1a2235',
        },
        border: {
          subtle: '#1E2D45',
          DEFAULT: '#253550',
        },
        brand: {
          DEFAULT: '#3B82F6',
          dim: '#1d4ed8',
          glow: 'rgba(59,130,246,0.15)',
        },
        violet: {
          ai: '#8B5CF6',
          dim: '#6d28d9',
          glow: 'rgba(139,92,246,0.15)',
        },
        success: {
          DEFAULT: '#10B981',
          dim: '#065f46',
          glow: 'rgba(16,185,129,0.15)',
        },
        warning: {
          DEFAULT: '#F59E0B',
          dim: '#92400e',
        },
        danger: {
          DEFAULT: '#EF4444',
          dim: '#7f1d1d',
        },
        text: {
          primary: '#F1F5F9',
          secondary: '#94A3B8',
          muted: '#475569',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(59,130,246,0.3), 0 0 20px rgba(59,130,246,0.1)',
        'glow-violet': '0 0 0 1px rgba(139,92,246,0.3), 0 0 20px rgba(139,92,246,0.1)',
        'glow-success': '0 0 0 1px rgba(16,185,129,0.3), 0 0 12px rgba(16,185,129,0.1)',
        card: '0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.25s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
