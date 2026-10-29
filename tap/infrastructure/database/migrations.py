import hashlib
import json

from mysql.connector import Error

from tap.core.date_utils import parse_mois_saisie
from tap.infrastructure.database.connection import obtenir_connexion


def initialiser_schema_si_absent():
    """Crée la base et les tables minimales si elles n'existent pas."""
    try:
        conn = obtenir_connexion()
        if conn is None or not conn.is_connected():
            return

        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS locataires (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nom VARCHAR(100) NOT NULL,
                prenom VARCHAR(100) NOT NULL,
                telephone VARCHAR(20) NULL,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_nom (nom),
                INDEX idx_prenom (prenom),
                INDEX idx_telephone (telephone)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS paiements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                locataire_id INT NOT NULL,
                mois DATE NOT NULL,
                montant DECIMAL(10, 2) NOT NULL,
                devise VARCHAR(10) NOT NULL,
                statut_souscription VARCHAR(20) DEFAULT 'Simple',
                statut VARCHAR(20) DEFAULT 'En attente',
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                montant_total DECIMAL(10, 2) DEFAULT 0,
                montant_paye DECIMAL(10, 2) DEFAULT 0,
                reste_a_payer DECIMAL(10, 2) DEFAULT 0,
                statut_paiement VARCHAR(20) DEFAULT 'En attente',
                CONSTRAINT fk_paiements_locataires
                    FOREIGN KEY (locataire_id) REFERENCES locataires(id)
                    ON DELETE CASCADE,
                INDEX idx_statut (statut),
                INDEX idx_statut_souscription (statut_souscription),
                INDEX idx_mois (mois),
                INDEX idx_devise (devise),
                INDEX idx_statut_paiement (statut_paiement),
                INDEX idx_locataire_mois_statut (locataire_id, mois, statut_souscription)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS maintenance_journal (
                id INT AUTO_INCREMENT PRIMARY KEY,
                operation_key VARCHAR(64) NOT NULL,
                period_key VARCHAR(16) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'running',
                created_count INT NOT NULL DEFAULT 0,
                error_count INT NOT NULL DEFAULT 0,
                details_json TEXT NULL,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                completed_at DATETIME NULL,
                UNIQUE KEY uq_operation_period (operation_key, period_key)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS portail_locataire_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                locataire_id INT NOT NULL,
                token_hash CHAR(64) NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                last_used_at DATETIME NULL,
                revoked_at DATETIME NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_portail_token_locataire
                    FOREIGN KEY (locataire_id) REFERENCES locataires(id)
                    ON DELETE CASCADE,
                INDEX idx_portail_token_locataire (locataire_id),
                INDEX idx_portail_token_expiration (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS offline_sync_events (
                event_id CHAR(36) PRIMARY KEY,
                device_id VARCHAR(100) NOT NULL,
                event_type VARCHAR(60) NOT NULL,
                payload_json TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                conflict_json TEXT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                synced_at DATETIME NULL,
                INDEX idx_sync_status (status),
                INDEX idx_sync_device (device_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(32) PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                checksum CHAR(64) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Error as e:
        print(f"Erreur lors de l'initialisation du schéma: {e}")
    finally:
        if "conn" in locals() and conn is not None and conn.is_connected():
            conn.close()


def ajouter_colonne_date_creation():
    """Ajoute date_creation aux tables qui l'utilisent."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()

            changed = False
            for table in ("locataires", "paiements"):
                cursor.execute(f"SHOW COLUMNS FROM {table} LIKE 'date_creation'")
                if not cursor.fetchone():
                    cursor.execute(
                        f"ALTER TABLE {table} "
                        "ADD COLUMN date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
                    changed = True
            if changed:
                conn.commit()
                print("Colonnes date_creation vérifiées et ajoutées si nécessaire")

            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de l'ajout de la colonne: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_colonne_statut_souscription():
    """Ajoute la colonne statut_souscription si elle n'existe pas."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()

            cursor.execute("SHOW COLUMNS FROM paiements LIKE 'statut_souscription'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE paiements ADD COLUMN statut_souscription VARCHAR(20) DEFAULT 'Simple' AFTER devise"
                )
                try:
                    cursor.execute(
                        "CREATE INDEX idx_statut_souscription ON paiements(statut_souscription)"
                    )
                except Error:
                    pass
                conn.commit()
                print("Colonne statut_souscription ajoutée avec succès")

            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de l'ajout de la colonne statut_souscription: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def migrer_mois_vers_date():
    """Convertit la colonne mois de VARCHAR vers DATE."""
    try:
        conn = obtenir_connexion()
        if not conn.is_connected():
            return

        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM paiements LIKE 'mois'")
        column = cursor.fetchone()
        if not column:
            cursor.close()
            conn.close()
            return

        column_type = str(column[1]).lower()
        if "date" in column_type and "datetime" not in column_type:
            cursor.close()
            conn.close()
            return

        cursor.execute("SELECT id, mois FROM paiements")
        rows = cursor.fetchall()
        parsed_rows = []
        invalid_ids = []

        for paiement_id, raw_mois in rows:
            try:
                parsed = parse_mois_saisie(raw_mois)
            except (TypeError, ValueError, OverflowError):
                parsed = None
            if parsed is None:
                invalid_ids.append(paiement_id)
            else:
                parsed_rows.append((parsed, paiement_id))

        # Ne jamais convertir silencieusement une date inconnue en date arbitraire.
        # On abandonne cette migration sans modifier les lignes si des valeurs
        # invalides existent; elles doivent être corrigées après sauvegarde.
        if invalid_ids:
            preview = ", ".join(str(value) for value in invalid_ids[:20])
            suffix = "..." if len(invalid_ids) > 20 else ""
            print(
                f"Migration mois -> DATE interrompue : {len(invalid_ids)} "
                f"valeur(s) invalide(s), identifiants : {preview}{suffix}"
            )
            cursor.close()
            conn.close()
            return

        for parsed, paiement_id in parsed_rows:
            cursor.execute(
                "UPDATE paiements SET mois = %s WHERE id = %s",
                (parsed, paiement_id),
            )

        conn.commit()
        cursor.execute("ALTER TABLE paiements MODIFY COLUMN mois DATE NOT NULL")
        conn.commit()
        print("Colonne mois migrée vers DATE avec succès")

        cursor.close()
        conn.close()
    except Error as e:
        print(f"Erreur lors de la migration mois -> DATE: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def renommer_statut_ordinaire_en_simple():
    """Remplace la valeur historique Ordinaire par Simple."""
    try:
        conn = obtenir_connexion()
        if not conn.is_connected():
            return

        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM paiements LIKE 'statut_souscription'")
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return

        cursor.execute(
            "UPDATE paiements SET statut_souscription = 'Simple' "
            "WHERE statut_souscription = 'Ordinaire'"
        )
        cursor.execute(
            "ALTER TABLE paiements MODIFY COLUMN statut_souscription "
            "VARCHAR(20) DEFAULT 'Simple'"
        )
        conn.commit()
        print("Statut souscription Ordinaire renommé en Simple")

        cursor.close()
        conn.close()
    except Error as e:
        print(f"Erreur lors du renommage Ordinaire -> Simple: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def renommer_statut_paye_en_en_regle():
    """Remplace la valeur de statut 'Payé' par 'En règle'."""
    try:
        conn = obtenir_connexion()
        if not conn.is_connected():
            return

        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM paiements LIKE 'statut'")
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return

        cursor.execute(
            "UPDATE paiements SET statut = 'En règle' "
            "WHERE statut = 'Payé'"
        )
        conn.commit()
        print("Statut Payé renommé en En règle")

        cursor.close()
        conn.close()
    except Error as e:
        print(f"Erreur lors du renommage Payé -> En règle: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_colonnes_acompte():
    """Ajoute les colonnes pour la gestion des acomptes."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()

            # Vérifier et ajouter montant_total
            cursor.execute("SHOW COLUMNS FROM paiements LIKE 'montant_total'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE paiements ADD COLUMN montant_total DECIMAL(10,2) DEFAULT montant"
                )
                # Initialiser montant_total avec la valeur actuelle de montant
                cursor.execute("UPDATE paiements SET montant_total = montant WHERE montant_total IS NULL")
                print("Colonne montant_total ajoutée avec succès")

            # Vérifier et ajouter montant_paye
            cursor.execute("SHOW COLUMNS FROM paiements LIKE 'montant_paye'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE paiements ADD COLUMN montant_paye DECIMAL(10,2) DEFAULT 0"
                )
                # Initialiser montant_paye avec la valeur actuelle de montant pour les enregistrements existants
                cursor.execute("UPDATE paiements SET montant_paye = montant WHERE montant_paye IS NULL OR montant_paye = 0")
                print("Colonne montant_paye ajoutée avec succès")

            # Vérifier et ajouter reste_a_payer
            cursor.execute("SHOW COLUMNS FROM paiements LIKE 'reste_a_payer'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE paiements ADD COLUMN reste_a_payer DECIMAL(10,2) DEFAULT 0"
                )
                # Calculer le reste initial
                cursor.execute("UPDATE paiements SET reste_a_payer = GREATEST(0, montant_total - montant_paye) WHERE reste_a_payer IS NULL OR reste_a_payer = 0")
                print("Colonne reste_a_payer ajoutée avec succès")

            # Vérifier et ajouter statut_paiement
            cursor.execute("SHOW COLUMNS FROM paiements LIKE 'statut_paiement'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE paiements ADD COLUMN statut_paiement VARCHAR(20) DEFAULT 'En attente'"
                )
                # Définir le statut initial
                cursor.execute(
                    "UPDATE paiements SET statut_paiement = "
                    "CASE "
                    "WHEN montant_paye >= montant_total THEN 'Complet' "
                    "WHEN montant_paye > 0 THEN 'Partiel' "
                    "ELSE 'En attente' "
                    "END WHERE statut_paiement IS NULL OR statut_paiement = 'En attente'"
                )

                # Mettre à jour le statut automatiquement selon le montant payé
                cursor.execute(
                    "UPDATE paiements SET statut = "
                    "CASE "
                    "WHEN montant_paye <= 0 THEN 'En attente' "
                    "WHEN montant_paye < montant_total THEN 'Litigieux' "
                    "ELSE 'En règle' "
                    "END"
                )
                print("Colonne statut_paiement ajoutée avec succès")

            conn.commit()

            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de l'ajout des colonnes acompte: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_index_locataire_mois_statut():
    """Ajoute un index composé utile aux vérifications mensuelles et aux contrôles d'existence."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()

            cursor.execute("SHOW INDEX FROM paiements WHERE Key_name = 'idx_locataire_mois_statut'")
            # SHOW INDEX peut retourner une ligne par colonne indexée. Il faut
            # consommer tout le résultat avant d'exécuter une nouvelle requête.
            if not cursor.fetchall():
                cursor.execute(
                    "CREATE INDEX idx_locataire_mois_statut ON paiements(locataire_id, mois, statut_souscription)"
                )
                conn.commit()
                print("Index idx_locataire_mois_statut ajouté avec succès")

            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de l'ajout de l'index locataire/mois/statut: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_table_maintenance_journal():
    """Crée la table de journalisation des maintenances automatiques."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()
            cursor.execute(
                """
                    CREATE TABLE IF NOT EXISTS maintenance_journal (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        operation_key VARCHAR(64) NOT NULL,
                        period_key VARCHAR(16) NOT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'running',
                        created_count INT NOT NULL DEFAULT 0,
                        error_count INT NOT NULL DEFAULT 0,
                        details_json TEXT NULL,
                        started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        completed_at DATETIME NULL,
                        UNIQUE KEY uq_operation_period (operation_key, period_key)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            conn.commit()
            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de la création de la table maintenance_journal: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_table_archives_paiements():
    """Crée la table archives_paiements pour stocker les vieux enregistrements."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()
            # On s'assure d'abord que la table n'existe pas déjà
            cursor.execute("SHOW TABLES LIKE 'archives_paiements'")
            if not cursor.fetchone():
                # On la crée avec la structure de 'paiements' (sans les données)
                cursor.execute("CREATE TABLE archives_paiements LIKE paiements")
                conn.commit()
                print("Table archives_paiements créée avec succès")
            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de la création de la table archives_paiements: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_table_loyer_tarifs():
    """Crée l'historique optionnel des tarifs applicables par locataire."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS loyer_tarifs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    locataire_id INT NOT NULL,
                    montant DECIMAL(10, 2) NOT NULL,
                    devise VARCHAR(10) NOT NULL,
                    effective_from DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (locataire_id) REFERENCES locataires(id) ON DELETE CASCADE,
                    INDEX idx_tarif_locataire_date (locataire_id, effective_from)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            conn.commit()
            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de la création de la table loyer_tarifs: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def ajouter_table_signatures_paiements():
    """Crée la table des signatures numériques liées aux paiements."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS signatures_paiements (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    paiement_id INT NOT NULL,
                    locataire_id INT NOT NULL,
                    document_hash VARCHAR(64) NOT NULL,
                    consentement TINYINT(1) NOT NULL DEFAULT 1,
                    signature_png LONGBLOB NOT NULL,
                    signataire_nom VARCHAR(201) NOT NULL,
                    signed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    signer_ip VARCHAR(45) NULL,
                    user_agent VARCHAR(255) NULL,
                    FOREIGN KEY (paiement_id) REFERENCES paiements(id) ON DELETE CASCADE,
                    FOREIGN KEY (locataire_id) REFERENCES locataires(id) ON DELETE CASCADE,
                    INDEX idx_signature_paiement (paiement_id),
                    INDEX idx_signature_locataire (locataire_id),
                    INDEX idx_signature_signed_at (signed_at)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            conn.commit()
            cursor.close()
            conn.close()
    except Error as e:
        print(f"Erreur lors de la création de la table signatures_paiements: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def verifier_coherence_donnees() -> dict[str, int]:
    """Effectue un contrôle non destructif avant/après une migration.

    Aucun enregistrement n'est corrigé ou supprimé automatiquement. Les
    anomalies sont comptées afin d'être sauvegardées dans le journal de
    migration et traitées avec une sauvegarde disponible.
    """
    result = {
        "paiements_orphelins": 0,
        "montants_invalides": 0,
        "restes_incoherents": 0,
        "signatures_orphelines": 0,
    }
    conn = None
    cursor = None
    try:
        conn = obtenir_connexion()
        if conn is None or not conn.is_connected():
            return result
        cursor = conn.cursor()
        checks = {
            "paiements_orphelins": (
                "SELECT COUNT(*) FROM paiements p "
                "LEFT JOIN locataires l ON l.id = p.locataire_id "
                "WHERE l.id IS NULL"
            ),
            "montants_invalides": (
                "SELECT COUNT(*) FROM paiements "
                "WHERE montant_total < 0 OR montant_paye < 0"
            ),
            "restes_incoherents": (
                "SELECT COUNT(*) FROM paiements "
                "WHERE ABS(COALESCE(reste_a_payer, 0) - "
                "GREATEST(0, COALESCE(montant_total, 0) - COALESCE(montant_paye, 0))) > 0.01"
            ),
            "signatures_orphelines": (
                "SELECT COUNT(*) FROM signatures_paiements s "
                "LEFT JOIN paiements p ON p.id = s.paiement_id "
                "WHERE p.id IS NULL"
            ),
        }
        for key, query in checks.items():
            try:
                cursor.execute(query)
                row = cursor.fetchone()
                result[key] = int(row[0] if row else 0)
            except Error:
                # La table de signatures peut être absente sur une ancienne
                # base ; la migration suivante la crée.
                result[key] = 0
        return result
    except Error as exc:
        print(f"Contrôle de cohérence indisponible : {exc}")
        return result
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


def normaliser_restes_non_negatifs() -> None:
    """Rétablit l'invariant métier : un reste à payer ne peut pas être négatif.

    Le montant payé n'est jamais modifié : un éventuel trop-perçu reste donc
    traçable et seul le champ dérivé ``reste_a_payer`` est recalculé.
    """
    conn = None
    cursor = None
    try:
        conn = obtenir_connexion()
        if conn is None or not conn.is_connected():
            return
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE paiements SET reste_a_payer = GREATEST(0, "
            "COALESCE(montant_total, 0) - COALESCE(montant_paye, 0)) "
            "WHERE reste_a_payer < 0"
        )
        if cursor.rowcount:
            print(f"{cursor.rowcount} reste(s) à payer négatif(s) normalisé(s)")
        conn.commit()
    except Error as exc:
        if conn is not None and conn.is_connected():
            conn.rollback()
        print(f"Normalisation des restes impossible : {exc}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


def enregistrer_version_schema(version: str, name: str, payload: dict) -> None:
    """Journalise une version de schéma de manière idempotente."""
    conn = None
    cursor = None
    try:
        conn = obtenir_connexion()
        if conn is None or not conn.is_connected():
            return
        cursor = conn.cursor()
        checksum = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        cursor.execute(
            "INSERT INTO schema_migrations (version, name, checksum) "
            "VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE checksum = VALUES(checksum)",
            (version, name, checksum),
        )
        conn.commit()
    except Error as exc:
        print(f"Journal de migration indisponible : {exc}")
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


def ajouter_index_unique_locataire_nom_prenom():
    """Empêche les doublons de locataires au niveau MySQL."""
    try:
        conn = obtenir_connexion()
        if conn.is_connected():
            cursor = conn.cursor()
            cursor.execute(
                "SHOW INDEX FROM locataires WHERE Key_name = 'uq_locataire_nom_prenom'"
            )
            if not cursor.fetchall():
                cursor.execute(
                    "CREATE UNIQUE INDEX uq_locataire_nom_prenom "
                    "ON locataires(nom, prenom)"
                )
                conn.commit()
                print("Contrainte unique nom/prénom ajoutée avec succès")
            cursor.close()
            conn.close()
    except Error as e:
        # Une ancienne base contenant déjà des doublons ne doit pas empêcher
        # l'application de démarrer : le contrôle applicatif reste actif.
        print(f"Contrainte unique locataire non ajoutée : {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            conn.close()


def run_migrations():
    initialiser_schema_si_absent()
    ajouter_colonne_date_creation()
    ajouter_colonne_statut_souscription()
    renommer_statut_ordinaire_en_simple()
    renommer_statut_paye_en_en_regle()
    migrer_mois_vers_date()
    ajouter_colonnes_acompte()
    normaliser_restes_non_negatifs()
    ajouter_index_locataire_mois_statut()
    ajouter_index_unique_locataire_nom_prenom()
    ajouter_table_maintenance_journal()
    ajouter_table_archives_paiements()
    ajouter_table_loyer_tarifs()
    ajouter_table_signatures_paiements()
    coherence = verifier_coherence_donnees()
    enregistrer_version_schema(
        "4.1.0",
        "responsive_qr_coherence",
        {"migrations": "4.1.0", "coherence": coherence},
    )
    return coherence
