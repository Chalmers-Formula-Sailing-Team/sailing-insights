class Job:
    """holds the information to process a session"""

    def __init__(self, session_path: str, meta_path: str):
        self.session_path = session_path
        self.meta_path = meta_path
