#!/bin/bash

# Chemin complet du script
script_path=$(realpath $0)

# Répertoire du script
script_dir=$(dirname $script_path)

# Modèle Makefile
template_file="${script_dir}/Makefile.template"

# Vérifier si le fichier Makefile.template existe
if [ ! -f "$template_file" ]; then
    echo "Erreur : Le fichier Makefile.template n'a pas été trouvé dans le même répertoire que le script."
    exit 1
fi

# Chemin du nouveau Makefile à créer
output_file="./Makefile"

# Fichier Makefile
if [ -f "$output_file" ]; then
    if [ "$1" = "-f" ] || [ "$1" = "--force" ]; then
        echo "Suppression du fichier Makefile existant."
        rm "$output_file"
    else
        echo "Erreur : Le fichier Makefile existe déjà dans le répertoire courant."
        exit 1
    fi
fi
cp "$template_file" "$output_file"

# Créer les dossier src, bin, build, debug/bin et debug/build
mkdir -p src bin build debug/bin debug/build

echo "Projet créé dans" $(realpath $output_file).
