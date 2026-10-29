"""
Tests unitaires pour le module d'authentification.

Ce module contient les tests pour le système d'authentification sécurisé
incluant le hashage des mots de passe et la gestion des tentatives.
"""

import os

import pytest
import tap.core.auth as auth_module
from tap.core.auth import AuthenticationManager, authenticate_user


class TestAuthenticationManager:
    """Tests pour le gestionnaire d'authentification."""
    
    def setup_method(self):
        """Initialise un gestionnaire avec un secret de test explicite."""
        os.environ["TAP_ADMIN_INITIAL_PASSWORD"] = "TestAdmin-Password-123"
        self.auth_manager = AuthenticationManager()
    
    def test_default_user_exists(self):
        """Teste que l'utilisateur par défaut existe."""
        assert "TAPADM" in self.auth_manager._users
    
    def test_default_user_authentication(self):
        """Teste l'authentification avec l'utilisateur par défaut."""
        success, message = self.auth_manager.authenticate("TAPADM", "TestAdmin-Password-123")
        assert success is True
        assert "réussie" in message.lower()
    
    def test_wrong_password(self):
        """Teste qu'un mauvais mot de passe est rejeté."""
        success, message = self.auth_manager.authenticate("TAPADM", "wrongpassword")
        assert success is False
        assert "incorrect" in message.lower()
    
    def test_wrong_username(self):
        """Teste qu'un mauvais nom d'utilisateur est rejeté."""
        success, message = self.auth_manager.authenticate("wronguser", "TAPADM")
        assert success is False
        assert "incorrect" in message.lower()
    
    def test_empty_credentials(self):
        """Teste que des identifiants vides sont rejetés."""
        success, message = self.auth_manager.authenticate("", "")
        assert success is False
        
        success, message = self.auth_manager.authenticate("TAPADM", "")
        assert success is False
        
        success, message = self.auth_manager.authenticate("", "TAPADM")
        assert success is False
    
    def test_password_hashing(self):
        """Teste que les mots de passe sont correctement hashés."""
        password = "testpassword123"
        hashed = self.auth_manager._hash_password(password)
        
        # Le hash doit contenir un sel et le hash
        assert ":" in hashed
        assert hashed != password
        
        # Vérifier que le même mot de passe produit le même hash
        assert self.auth_manager._verify_password(password, hashed) is True
    
    def test_password_verification(self):
        """Teste la vérification des mots de passe."""
        password = "testpassword123"
        hashed = self.auth_manager._hash_password(password)
        
        assert self.auth_manager._verify_password(password, hashed) is True
        assert self.auth_manager._verify_password("wrongpassword", hashed) is False
    
    def test_add_user(self):
        """Teste l'ajout d'un nouvel utilisateur."""
        success, message = self.auth_manager.add_user("newuser", "password123")
        assert success is True
        assert "newuser" in self.auth_manager._users
        
        # Teste l'authentification avec le nouvel utilisateur
        success, _ = self.auth_manager.authenticate("newuser", "password123")
        assert success is True
    
    def test_add_duplicate_user(self):
        """Teste qu'on ne peut pas ajouter un utilisateur existant."""
        success, message = self.auth_manager.add_user("TAPADM", "newpassword")
        assert success is False
        assert "existe déjà" in message.lower()
    
    def test_add_user_short_password(self):
        """Teste qu'on ne peut pas ajouter un utilisateur avec un mot de passe trop court."""
        success, message = self.auth_manager.add_user("newuser", "short")
        assert success is False
        assert "au moins 8 caractères" in message.lower()
    
    def test_change_password(self):
        """Teste le changement de mot de passe."""
        old_password = "TestAdmin-Password-123"
        new_password = "newpassword123"
        
        success, message = self.auth_manager.change_password("TAPADM", old_password, new_password)
        assert success is True
        
        # Vérifier que l'ancien mot de passe ne fonctionne plus
        success, _ = self.auth_manager.authenticate("TAPADM", old_password)
        assert success is False
        
        # Vérifier que le nouveau mot de passe fonctionne
        success, _ = self.auth_manager.authenticate("TAPADM", new_password)
        assert success is True
    
    def test_change_password_wrong_old_password(self):
        """Teste qu'on ne peut pas changer le mot de passe avec un mauvais ancien mot de passe."""
        success, message = self.auth_manager.change_password("TAPADM", "wrongpassword", "newpassword")
        assert success is False
        assert "incorrect" in message.lower()
    
    def test_change_password_short_new_password(self):
        """Teste qu'on ne peut pas mettre un mot de passe trop court."""
        success, message = self.auth_manager.change_password("TAPADM", "TestAdmin-Password-123", "short")
        assert success is False
        assert "au moins 8 caractères" in message.lower()
    
    def test_deactivate_user(self):
        """Teste la désactivation d'un utilisateur."""
        success, message = self.auth_manager.deactivate_user("TAPADM")
        assert success is True
        
        # Vérifier que l'utilisateur ne peut plus s'authentifier
        success, message = self.auth_manager.authenticate("TAPADM", "TAPADM")
        assert success is False
        assert "désactivé" in message.lower()
    
    def test_deactivate_nonexistent_user(self):
        """Teste qu'on ne peut pas désactiver un utilisateur inexistant."""
        success, message = self.auth_manager.deactivate_user("nonexistent")
        assert success is False
        assert "non trouvé" in message.lower()
    
    def test_failed_attempts_tracking(self):
        """Teste le suivi des tentatives échouées."""
        # Faire plusieurs tentatives échouées
        for _ in range(3):
            self.auth_manager.authenticate("TAPADM", "wrongpassword")
        
        assert "TAPADM" in self.auth_manager._failed_attempts
        assert self.auth_manager._failed_attempts["TAPADM"][0] == 3
    
    def test_account_lockout(self):
        """Teste le verrouillage du compte après trop de tentatives."""
        # Faire 5 tentatives échouées (le maximum)
        for _ in range(5):
            self.auth_manager.authenticate("TAPADM", "wrongpassword")
        
        # Le compte devrait être verrouillé
        success, message = self.auth_manager.authenticate("TAPADM", "TAPADM")
        assert success is False
        assert "verrouillé" in message.lower()
    
    def test_get_user_info(self):
        """Teste la récupération des informations utilisateur."""
        user_info = self.auth_manager.get_user_info("TAPADM")
        
        assert user_info is not None
        assert user_info["username"] == "TAPADM"
        assert "created_at" in user_info
        assert "is_active" in user_info
        assert "password_hash" not in user_info  # Le mot de passe ne doit pas être inclus
    
    def test_get_nonexistent_user_info(self):
        """Teste la récupération d'informations pour un utilisateur inexistant."""
        user_info = self.auth_manager.get_user_info("nonexistent")
        assert user_info is None

    def test_new_password_hash_uses_scrypt(self):
        hashed = self.auth_manager._hash_password("strong-password-123")
        assert hashed.startswith("scrypt$")
        assert self.auth_manager._verify_password("strong-password-123", hashed)
        assert not self.auth_manager._verify_password("wrong-password", hashed)

    def test_legacy_sha256_hash_is_upgraded_after_login(self):
        import hashlib
        salt = "legacy-salt"
        old_hash = f"{salt}:" + hashlib.sha256(("TAPADM" + salt).encode()).hexdigest()
        self.auth_manager._users["legacy-user"] = {
            "password_hash": old_hash,
            "created_at": None,
            "last_login": None,
            "is_active": True,
        }
        # Set a compatible legacy hash for the actual test user's password.
        password = "legacy-password"
        self.auth_manager._users["legacy-user"]["password_hash"] = (
            f"{salt}:" + hashlib.sha256((password + salt).encode()).hexdigest()
        )
        success, _ = self.auth_manager.authenticate("legacy-user", password)
        assert success is True
        assert self.auth_manager._users["legacy-user"]["password_hash"].startswith("scrypt$")


class TestAuthenticateUser:
    """Tests pour la fonction utilitaire d'authentification."""
    
    def test_authenticate_user_success(self, monkeypatch):
        """Teste l'authentification réussie via la fonction utilitaire."""
        monkeypatch.setenv("TAP_ADMIN_INITIAL_PASSWORD", "TestAdmin-Password-123")
        monkeypatch.setattr(auth_module, "auth_manager", AuthenticationManager())
        success, message = authenticate_user("TAPADM", "TestAdmin-Password-123")
        assert success is True
    
    def test_authenticate_user_failure(self, monkeypatch):
        """Teste l'échec de l'authentification via la fonction utilitaire."""
        monkeypatch.setenv("TAP_ADMIN_INITIAL_PASSWORD", "TestAdmin-Password-123")
        monkeypatch.setattr(auth_module, "auth_manager", AuthenticationManager())
        success, message = authenticate_user("TAPADM", "wrongpassword")
        assert success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
