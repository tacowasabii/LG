/** @type {import('tailwindcss').Config} */

/*
 * Tailwind 테마를 디자인 시스템 토큰(src/index.css의 :root)과 같은 값으로 맞춘다.
 * 같은 색을 유틸리티(bg-ink-50)로도, 인라인 스타일(var(--ink-50))로도 쓸 수 있어야
 * 계산으로 정해지는 값과 고정된 값을 한 화면에서 섞어 쓸 수 있다.
 *
 * gray와 primary 별칭은 두지 않는다. 화면 코드에서 그 이름은 이미 다 걷어냈고,
 * 별칭을 남겨 두면 옛 팔레트로 되돌아갈 길을 열어 두는 셈이 된다.
 */

const ink = {
  50: '#F2F1EC',
  100: '#E5E3DC',
  200: '#C9C6BC',
  300: '#9C988C',
  400: '#6E6A60',
  500: '#3F3C36',
  600: '#2F2C28',
  700: '#1F1D1A',
  800: '#161510',
  900: '#0E0D0B',
}

const accent = {
  DEFAULT: '#8A1538',
  ink: '#A61E4D',
  deep: '#5F0E26',
  soft: '#F4E3E8',
  fg: '#FFFFFF',
  'on-dark': '#E5809B',
  'on-dark-ink': '#F2C4CF',
}

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: { DEFAULT: '#FAFAF7', pure: '#FFFFFF' },
        ink,
        accent,
        positive: { DEFAULT: '#17766B', ink: '#115B52', soft: '#DFEEEC' },
        warning: { DEFAULT: '#7C5CB0', ink: '#634790', soft: '#ECE6F5' },
        critical: { DEFAULT: '#C2542A', ink: '#9C4220', soft: '#F6E6DE' },
        border: { DEFAULT: ink[100], strong: ink[200] },
      },
      borderColor: {
        DEFAULT: ink[100],
      },
      fontFamily: {
        sans: [
          '"Pretendard Variable"',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'system-ui',
          'sans-serif',
        ],
        mono: ['"JetBrains Mono"', 'ui-monospace', '"SF Mono"', 'Menlo', 'monospace'],
      },
      letterSpacing: {
        display: '-0.025em',
        eyebrow: '0.14em',
      },
      borderRadius: {
        DEFAULT: '8px',
        lg: '12px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(14,13,11,0.04), 0 1px 1px rgba(14,13,11,0.03)',
        DEFAULT: '0 4px 12px rgba(14,13,11,0.06), 0 2px 4px rgba(14,13,11,0.04)',
        md: '0 4px 12px rgba(14,13,11,0.06), 0 2px 4px rgba(14,13,11,0.04)',
        lg: '0 12px 32px rgba(14,13,11,0.08), 0 4px 8px rgba(14,13,11,0.04)',
      },
      transitionTimingFunction: {
        out: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
