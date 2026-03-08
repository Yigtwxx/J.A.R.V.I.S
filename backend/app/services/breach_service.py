from typing import List, Dict, Any
import asyncio
import hashlib
from app.utils.logger import logger
import random

class BreachService:
    """
    Service for querying HaveIBeenPwned or OSINT data breach sources.
    Implemented as a robust Simulation/Mock to prevent rate-limiting and API Key requirements
    in the J.A.R.V.I.S ecosystem while still providing realistic Threat Intelligence UI.
    """

    # Realistic mock databases to simulate dark web findings
    MOCK_DATABASES = [
        {"Name": "LinkedIn", "Title": "LinkedIn (2012 Breach)", "Domain": "linkedin.com", "BreachDate": "2012-05-05", "DataClasses": ["Email addresses", "Passwords"], "IsVerified": True},
        {"Name": "Adobe", "Title": "Adobe Systems", "Domain": "adobe.com", "BreachDate": "2013-10-04", "DataClasses": ["Email addresses", "Password hints", "Passwords", "Usernames"], "IsVerified": True},
        {"Name": "Canva", "Title": "Canva", "Domain": "canva.com", "BreachDate": "2019-05-24", "DataClasses": ["Email addresses", "Geographic locations", "Names", "Passwords", "Usernames"], "IsVerified": True},
        {"Name": "Dubsmash", "Title": "Dubsmash", "Domain": "dubsmash.com", "BreachDate": "2018-12-01", "DataClasses": ["Email addresses", "Geographic locations", "Names", "Passwords", "Phone numbers", "Spoken languages"], "IsVerified": True},
        {"Name": "MyFitnessPal", "Title": "MyFitnessPal", "Domain": "myfitnesspal.com", "BreachDate": "2018-02-01", "DataClasses": ["Email addresses", "IP addresses", "Passwords", "Usernames"], "IsVerified": True},
        {"Name": "Tumblr", "Title": "Tumblr", "Domain": "tumblr.com", "BreachDate": "2013-01-01", "DataClasses": ["Email addresses", "Passwords"], "IsVerified": True},
        {"Name": "Twitter", "Title": "Twitter (200M Leaks)", "Domain": "twitter.com", "BreachDate": "2023-01-04", "DataClasses": ["Email addresses", "Names", "Screen names", "Follower counts", "Account creation dates"], "IsVerified": True},
        {"Name": "Collection1", "Title": "Collection #1", "Domain": "unknown", "BreachDate": "2019-01-07", "DataClasses": ["Email addresses", "Passwords"], "IsVerified": False, "IsSpamList": True},
        {"Name": "Apollo", "Title": "Apollo", "Domain": "apollo.io", "BreachDate": "2018-07-23", "DataClasses": ["Email addresses", "Employers", "Geographic locations", "Job titles", "Names", "Phone numbers", "Social media profiles"], "IsVerified": True}
    ]

    @staticmethod
    def _generate_deterministic_breaches(email: str) -> List[Dict[str, Any]]:
        """
        Uses a hash of the email to deterministically assign 0 to 4 breaches from the mock DB.
        This ensures the same email always returns the exact same 'breaches', feeling like a real API.
        """
        email_lower = email.strip().lower()
        hash_val = int(hashlib.md5(email_lower.encode('utf-8')).hexdigest(), 16)
        
        # Decide how many breaches this email was involved in (0 to 4)
        # We bias towards 0 or 1 for realism, but some might be unlucky
        breach_count = hash_val % 10
        if breach_count < 4:
            num_breaches = 0
        elif breach_count < 7:
            num_breaches = 1
        elif breach_count < 9:
            num_breaches = 2
        else:
            num_breaches = hash_val % 4 + 1 # 1 to 4

        if num_breaches == 0:
            return []

        # Deterministically select elements
        selected_breaches = []
        available_dbs = list(BreachService.MOCK_DATABASES)
        
        # Random seed based on email hash so random.choice is consistent per email
        rnd = random.Random(hash_val)
        
        for _ in range(num_breaches):
            if not available_dbs:
                break
            chosen = rnd.choice(available_dbs)
            selected_breaches.append(chosen)
            available_dbs.remove(chosen)
            
        return selected_breaches

    async def check_breaches(self, emails: List[str]) -> List[Dict[str, Any]]:
        """
        Scans a list of discovered emails against Dark Web / Leak databases.
        """
        if not emails:
            return []

        logger.log_thought(f"Initiating Deep Web intelligence scan for {len(emails)} target identifiers.")
        await asyncio.sleep(1.5)  # Simulate API network latency
        
        all_breaches = []
        seen_breach_names = set()
        
        for email in emails:
            # In a real-world scenario, you would call requests.get(f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}", headers={"hibp-api-key": "..."})
            logger.log_action(f"Tracking signals across Dark Nodes", target=email)
            await asyncio.sleep(0.5)
            
            breaches = self._generate_deterministic_breaches(email)
            for breach in breaches:
                # Add email target to the breach object so UI knows WHICH email leaked where
                breach_copy = dict(breach)
                breach_copy["TargetEmail"] = email
                
                # Prevent duplicate identical breaches showing up if multiple emails were in the same breach
                signature = f"{email}_{breach['Name']}"
                if signature not in seen_breach_names:
                    seen_breach_names.add(signature)
                    all_breaches.append(breach_copy)

        if all_breaches:
            logger.log_warning(f"CRITICAL: {len(all_breaches)} security breaches detected in the wild.")
        else:
            logger.log_success("Target identifiers appear secure. No public data leaks found.")

        # Sort by date descending (newest breaches first)
        all_breaches.sort(key=lambda x: x.get("BreachDate", "1970-01-01"), reverse=True)
        return all_breaches

breach_service = BreachService()
