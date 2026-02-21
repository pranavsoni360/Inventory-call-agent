class IntentParser:

    def parse(self, text: str):

        text = text.lower()

        if any(w in text for w in ["bye", "stop", "hang up"]):
            return "EXIT"

        if any(w in text for w in ["what did i order", "show order", "items added"]):
            return "SHOW_ORDER"

        if any(w in text for w in ["yes", "confirm", "ok"]):
            return "AFFIRM"

        if any(w in text for w in ["no", "change"]):
            return "DENY"

        if any(w in text for w in ["repeat", "again"]):
            return "REPEAT"

        return "ORDER_INFO"
