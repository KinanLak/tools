const { merge } = require('webpack-merge'); // Fusionne les configurations communes et spécifiques à l'environnement
const common = require('./webpack.common.js'); // Importation de la configuration commune
const path = require('path');

module.exports = merge(common, {
  mode: 'development', // Définit le mode en développement, active des outils comme la source map
  devtool: 'inline-source-map', // Active une source map pour faciliter le débogage (lie le code minifié au code source)
  devServer: {
    static: './dist', // Répertoire à servir (ici, le répertoire 'dist')
    port: 3000, // Définit le port du serveur de développement
    open: true, // Ouvre automatiquement le navigateur lorsque le serveur démarre
    hot: true, // Active le hot module replacement (HMR), pour recharger le code sans rafraîchir la page entière
    // Optional: configuration proxy pour les API durant le développement
    // proxy: {
    //   '/api': 'http://localhost:5000'
    // },
  },
  output: {
    filename: 'bundle.js', // Nom du bundle en développement (généralement simple)
  },
});

