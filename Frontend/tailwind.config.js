/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{html,js}"
  ],
  theme: {
    extend: {
      colors: {
        'hlb-red': '#B91C1C',
        'hlb-bg': '#FDF2F2',
        'hlb-pink': '#FEE2E2',
      },
    },
  },
  plugins: [],
}
