module.exports = {
  // Enable dark mode
  darkMode: 'media',

  // Specify the paths to all of the template files in your project
  purge: ['./src/**/*.{js,jsx,ts,tsx}', './public/index.html'],

  // Extend the default theme
  theme: {
    extend: {
      screens: {
        // Mobile first breakpoints, screens can be added here
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
      },
      // Custom utilities
      colors: {
        'custom-color': '#1c1c1e',
      },
    },
  },

  // Plugins
  plugins: [],
};