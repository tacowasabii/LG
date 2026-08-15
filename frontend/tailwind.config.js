/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#fdf2f4',
          100: '#fce7eb',
          200: '#f9d0d9',
          300: '#f4a8b8',
          400: '#ed7491',
          500: '#e1476e',
          600: '#a50034', // LG Red
          700: '#8c002c',
          800: '#750025',
          900: '#630022',
        },
        gray: {
          50: '#f8f8f8',
          100: '#f0f0f0',
          200: '#e4e4e4',
          300: '#d1d1d1',
          400: '#9a9a9a',
          500: '#6b6b6b', // LG Grey
          600: '#5a5a5a',
          700: '#4a4a4a',
          800: '#3a3a3a',
          900: '#2a2a2a',
        },
      },
      fontFamily: {
        sans: ['"Noto Sans KR"', '"Inter"', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
