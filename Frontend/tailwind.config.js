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
        "primary": "#DC2626",
        "primary-dark": "#7F1D1D",
      },
      backgroundImage: {
        "gradient-red": "linear-gradient(135deg, #DC2626 0%, #991B1B 100%)",
        "gradient-subtle": "linear-gradient(135deg, #FEF2F2 0%, #FFF5F5 100%)",
      },
      boxShadow: {
        "card": "0 10px 30px rgba(0, 0, 0, 0.1)",
        "card-hover": "0 20px 40px rgba(0, 0, 0, 0.15)",
        "input": "0 2px 8px rgba(0, 0, 0, 0.05)",
      },
      animation: {
        "fade-in": "fadeIn 0.6s ease-in-out",
        "slide-up": "slideUp 0.6s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(20px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
      transitionDuration: {
        "350": "350ms",
      },
    },
  },
  plugins: [],
};
