# Security

Do not post credentials or customer data in public issues. Use GitHub private vulnerability reporting where available; otherwise contact the repository owner through their GitHub profile to arrange a private channel before sharing details.

The bridge holds operator credentials in process memory and can update native profiles and agents. Use a dedicated account, restrict config/state permissions and obtain credentials from your secret manager. SQLite contains private operational names and identifiers.

Each scope pairs one company with an isolated installation. Profiles are not a tenant security boundary. The bridge does not sandbox tools or synchronize authorization. Only 0.1.x is currently maintained; live qualification limits are in README.
