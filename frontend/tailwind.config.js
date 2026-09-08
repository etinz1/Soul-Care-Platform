/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      // "Bold Faith" brand palette — deep purple/burgundy against crisp
      // white and black, used for the entry points (login/register) and the
      // portal masthead (NavBar). Dashboard bodies intentionally stay on
      // the plain slate/white utility colors — see NavBar.jsx and
      // LoginPage.jsx/RegisterPage.jsx for where this is actually used.
      colors: {
        brand: {
          ink: "#150A1F",
          purple: "#3B0764",
          purpledark: "#1E0438",
          burgundy: "#5B0E2D",
          crimson: "#9B1B4A",
        },
      },
      fontFamily: {
        display: ['"Fraunces"', "ui-serif", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
