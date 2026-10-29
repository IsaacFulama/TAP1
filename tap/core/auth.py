"""
Module d'authentification sécurisée avec hashage de mots de passe.

Ce module fournit une gestion sécurisée de l'authentification des utilisateurs
en utilisant bcrypt pour le hashage des mots de passe.
"""

import hashlib
import os
import secrets
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AuthenticationManager:
    """Gestionnaire d'authentification avec hashage sécurisé des mots de passe."""
    
    def __init__(self):
        self._users = {}
        self._failed_attempts = {}
        self._lockout_duration = timedelta(minutes=15)
        self._max_attempts = 5
        self._initialize_default_user()
    
    def _initialize_default_user(self) -> None:
        """Crée l'administrateur initial uniquement si un secret est configuré."""
        username = os.getenv("TAP_ADMIN_INITIAL_USERNAME", "TAPADM").strip()
        password = os.getenv("TAP_ADMIN_INITIAL_PASSWORD", "")
        if not username or len(password) < 12:
            logger.error(
                "Aucun administrateur initial créé : configurez TAP_ADMIN_INITIAL_PASSWORD "
                "avec au moins 12 caractères avant de lancer l'application."
            )
            return

        self._users[username] = {
            "password_hash": self._hash_password(password),
            "created_at": datetime.now(),
            "last_login": None,
            "is_active": True,
        }
        logger.info("Compte administrateur initial créé depuis la configuration d'environnement.")

    def _hash_password(self, password: str) -> str:
        """Hash un mot de passe avec scrypt, conçu pour ralentir les attaques hors ligne."""
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
        )
        return "scrypt$" + salt.hex() + "$" + digest.hex()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Vérifie un hash scrypt ou un ancien hash SHA-256 pour permettre la migration."""
        try:
            if password_hash.startswith("scrypt$"):
                algorithm, salt_hex, stored_hash = password_hash.split("$")
                if algorithm != "scrypt":
                    return False
                salt = bytes.fromhex(salt_hex)
                computed = hashlib.scrypt(
                    password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
                ).hex()
                return secrets.compare_digest(computed, stored_hash)

            # Compatibilité transitoire : les anciens hashes sont migrés à la
            # première authentification réussie dans authenticate().
            salt_hex, stored_hash = password_hash.split(":")
            computed = hashlib.sha256((password + salt_hex).encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed, stored_hash)
        except (ValueError, AttributeError, TypeError):
            return False

    def _is_account_locked(self, username: str) -> bool:
        """
        Vérifie si un compte est verrouillé suite à trop de tentatives.
        
        Args:
            username: Nom d'utilisateur
            
        Returns:
            bool: True si le compte est verrouillé
        """
        if username not in self._failed_attempts:
            return False
        
        attempts, lock_time = self._failed_attempts[username]
        if attempts >= self._max_attempts:
            if datetime.now() - lock_time < self._lockout_duration:
                return True
            else:
                # Réinitialiser après la période de verrouillage
                del self._failed_attempts[username]
        
        return False
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Authentifie un utilisateur.
        
        Args:
            username: Nom d'utilisateur
            password: Mot de passe
            
        Returns:
            Tuple[bool, str]: (succès, message)
        """
        # Vérifier si le compte est verrouillé
        if self._is_account_locked(username):
            remaining_time = self._lockout_duration - (datetime.now() - self._failed_attempts[username][1])
            minutes = int(remaining_time.total_seconds() / 60)
            return False, f"Compte verrouillé. Réessayez dans {minutes} minutes."
        
        # Vérifier si l'utilisateur existe
        if username not in self._users:
            self._record_failed_attempt(username)
            return False, "Nom d'utilisateur ou mot de passe incorrect"
        
        user = self._users[username]
        
        # Vérifier si le compte est actif
        if not user["is_active"]:
            return False, "Ce compte est désactivé"
        
        # Vérifier le mot de passe
        if self._verify_password(password, user["password_hash"]):
            # Migration progressive des anciens hashes SHA-256 vers scrypt.
            if not user["password_hash"].startswith("scrypt$"):
                user["password_hash"] = self._hash_password(password)

            # Réinitialiser les tentatives échouées
            if username in self._failed_attempts:
                del self._failed_attempts[username]
            
            # Mettre à jour la dernière connexion
            user["last_login"] = datetime.now()
            logger.info(f"Utilisateur {username} connecté avec succès")
            return True, "Connexion réussie"
        
        # Enregistrer la tentative échouée
        self._record_failed_attempt(username)
        return False, "Nom d'utilisateur ou mot de passe incorrect"
    
    def _record_failed_attempt(self, username: str) -> None:
        """Enregistre une tentative de connexion échouée."""
        if username not in self._failed_attempts:
            self._failed_attempts[username] = [0, datetime.now()]
        
        self._failed_attempts[username][0] += 1
        self._failed_attempts[username][1] = datetime.now()
        
        attempts = self._failed_attempts[username][0]
        logger.warning(f"Tentative échouée pour {username}. Tentatives: {attempts}/{self._max_attempts}")
    
    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        Change le mot de passe d'un utilisateur.
        
        Args:
            username: Nom d'utilisateur
            old_password: Ancien mot de passe
            new_password: Nouveau mot de passe
            
        Returns:
            Tuple[bool, str]: (succès, message)
        """
        if username not in self._users:
            return False, "Utilisateur non trouvé"
        
        user = self._users[username]
        
        # Vérifier l'ancien mot de passe
        if not self._verify_password(old_password, user["password_hash"]):
            return False, "Ancien mot de passe incorrect"
        
        # Valider le nouveau mot de passe
        if len(new_password) < 8:
            return False, "Le nouveau mot de passe doit contenir au moins 8 caractères"
        
        # Hasher et stocker le nouveau mot de passe
        user["password_hash"] = self._hash_password(new_password)
        logger.info(f"Mot de passe changé pour l'utilisateur {username}")
        return True, "Mot de passe changé avec succès"
    
    def add_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        Ajoute un nouvel utilisateur.
        
        Args:
            username: Nom d'utilisateur
            password: Mot de passe
            
        Returns:
            Tuple[bool, str]: (succès, message)
        """
        if username in self._users:
            return False, "Cet utilisateur existe déjà"
        
        if len(password) < 8:
            return False, "Le mot de passe doit contenir au moins 8 caractères"
        
        self._users[username] = {
            "password_hash": self._hash_password(password),
            "created_at": datetime.now(),
            "last_login": None,
            "is_active": True
        }
        logger.info(f"Nouvel utilisateur créé: {username}")
        return True, "Utilisateur créé avec succès"
    
    def deactivate_user(self, username: str) -> Tuple[bool, str]:
        """
        Désactive un utilisateur.
        
        Args:
            username: Nom d'utilisateur
            
        Returns:
            Tuple[bool, str]: (succès, message)
        """
        if username not in self._users:
            return False, "Utilisateur non trouvé"
        
        self._users[username]["is_active"] = False
        logger.info(f"Utilisateur désactivé: {username}")
        return True, "Utilisateur désactivé"
    
    def get_user_info(self, username: str) -> Optional[dict]:
        """
        Récupère les informations d'un utilisateur (sans le mot de passe).
        
        Args:
            username: Nom d'utilisateur
            
        Returns:
            Optional[dict]: Informations de l'utilisateur ou None
        """
        if username not in self._users:
            return None
        
        user = self._users[username]
        return {
            "username": username,
            "created_at": user["created_at"],
            "last_login": user["last_login"],
            "is_active": user["is_active"]
        }


# Instance globale du gestionnaire d'authentification
auth_manager = AuthenticationManager()


def authenticate_user(username: str, password: str) -> Tuple[bool, str]:
    """
    Fonction utilitaire pour authentifier un utilisateur.
    
    Args:
        username: Nom d'utilisateur
        password: Mot de passe
        
    Returns:
        Tuple[bool, str]: (succès, message)
    """
    return auth_manager.authenticate(username, password)
