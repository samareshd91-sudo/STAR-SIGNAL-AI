import os
import logging
import google.generativeai as genai

logger = logging.getLogger("BG_STAR_PRO_AI")

class GeminiAIEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Updated to current stable model
            self.model_name = 'gemini-2.5-flash'
        else:
            logger.warning("⚠️ Gemini API Key is missing!")

    def evaluate_signal(self, coin: str, tech_data: dict, news_data: dict) -> dict:
        """
        Stage 4: Gemini AI Confirmation
        """
        if not self.api_key:
            return {"action": "WAIT", "confidence": 0, "reason": "No Gemini API Key."}

        prompt = (
            f"Analyze crypto asset {coin}.\n"
            f"Technical Direction: {tech_data['direction']}, Score: {tech_data['technical_score']}/100\n"
            f"Triggers: {', '.join(tech_data['trigger_reasons'])}\n"
            f"News Sentiment: {news_data['sentiment']}\n"
            f"News Context: {news_data['context']}\n"
            "Provide your final decision in strict format: ACTION: BUY/SELL/WAIT, CONFIDENCE: [0-100], REASON: [short text]"
        )

        try:
            logger.info(f"🤖 Gemini API Triggered for {coin}. Analyzing...")
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            text = response.text.upper()

            action = "WAIT"
            if "BUY" in text: action = "BUY"
            elif "SELL" in text: action = "SELL"

            return {
                "action": action,
                "confidence": 90,
                "reason": response.text[:150]
            }
        except Exception as e:
            logger.error(f"🛑 Gemini API Error: {e}")
            return {"action": "WAIT", "confidence": 0, "reason": "API Exception"}
