class StateMachine:

    def transition(self, state, intent, user_text):

        if state is None:
            return "GREETING", "Hello, this is your monthly ration reminder call.", None

        if intent == "CONFUSED":
            return state, "I’m calling to help you place your order.", None

        if state == "GREETING":
            return "ASK_ORDER", "What items would you like this month?", None

        if state == "ASK_ORDER":
            if intent == "ORDER_INFO":
                return "CONFIRM", f"I noted: {user_text}. Should I confirm?", user_text
            return "ASK_ORDER", "Please tell me the items you need.", None

        if state == "CONFIRM":

            if intent == "AFFIRM":
                return "END", "Your order is confirmed. Thank you.", None

            if intent == "DENY":
                return "ASK_ORDER", "Okay, please tell me again.", None

            return "CONFIRM", "Should I confirm the order?", None

        return "END", None, None
