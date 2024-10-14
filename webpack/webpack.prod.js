const { merge } = require('webpack-merge'); // Fusionne les configurations
const common = require('./webpack.common.js'); // Importation de la configuration commune
const TerserPlugin = require('terser-webpack-plugin'); // Plugin pour minifier le JavaScript
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin'); // Plugin pour minifier le CSS

module.exports = merge(common, {
  mode: 'production', // Définit le mode en production, active l'optimisation par défaut (comme la minification)
  output: {
    filename: 'bundle.[contenthash].js', // Utilisation de contenthash pour le cache-busting (force le navigateur à recharger les fichiers modifiés)
  },
  optimization: {
    minimize: true, // Active la minification pour réduire la taille des fichiers
    minimizer: [
      new TerserPlugin({ 
        parallel: true, // Minification JavaScript en parallèle pour accélérer le processus
        terserOptions: {
          compress: true, // Compression du code pour améliorer les performances
        },
      }),
      new CssMinimizerPlugin(), // Minification des fichiers CSS
    ],
    splitChunks: {
      chunks: 'all', // Divise le code en morceaux séparés (vendor, app, etc.) pour une meilleure gestion du cache
    },
  },
  // Rarely used: CompressionPlugin pour compresser les fichiers en Gzip ou Brotli
  // plugins: [
  //   new CompressionPlugin({
  //     algorithm: 'gzip',
  //   }),
  // ],
});

