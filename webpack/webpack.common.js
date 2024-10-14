const path = require('path'); // Utilisé pour travailler avec les chemins de fichiers
const HtmlWebpackPlugin = require('html-webpack-plugin'); // Plugin pour générer automatiquement un fichier HTML qui inclut les bundles

module.exports = {
  entry: './src/index.js', // Point d'entrée de l'application, ici le fichier principal JavaScript
  output: {
    filename: 'bundle.js', // Nom du fichier de sortie pour le bundle généré
    path: path.resolve(__dirname, 'dist'), // Répertoire de sortie (généralement 'dist' pour distribution)
    clean: true, // Nettoie le répertoire de sortie avant chaque build
  },
  module: {
    rules: [
      {
        test: /\.js$/, // Utilise cette règle pour tous les fichiers avec l'extension .js
        exclude: /node_modules/, // Ignore les fichiers dans node_modules
        use: {
          loader: 'babel-loader', // Utilise Babel pour transpiler le code ES6+ vers ES5 pour compatibilité
        },
      },
      {
        test: /\.(css|scss)$/, // Fichiers styles
        use: ['style-loader', 'css-loader', 'sass-loader'], // 'style-loader' injecte les styles dans le DOM, 'css-loader' interprète @import et url() comme import/require
      },
      {
        test: /\.(png|svg|jpg|jpeg|gif|ico)$/i, // Gestion des fichiers images
        type: 'asset/resource', // Gère les fichiers statiques comme des ressources (ils sont copiés dans 'dist')
      },
    ],
  },
  plugins: [
    new HtmlWebpackPlugin({
      //template: './src/index.html', // Utilise un fichier HTML comme modèle pour générer le fichier final
      favicon: path.resolve(__dirname, './src/images/favicon.ico')
    }),
  ],
  resolve: {
    extensions: ['.js'], // Extensions à résoudre automatiquement (par défaut '.js')
    // Optional: ajouter d'autres extensions comme '.jsx' ou '.ts' si besoin
    // extensions: ['.js', '.jsx', '.ts'],
  },
};

