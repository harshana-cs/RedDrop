/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{html,js}",   // all your HTML & JS files
  ],
  theme: {
    extend: {
      colors: {
        "hlb-red": "#B91C1C",
        "hlb-bg": "#FFF5F5",
        "hlb-lightRed": "#FEE2E2",
        "hlb-darkRed": "#991B1B",
      },
    },
  },
  plugins: [],
};
