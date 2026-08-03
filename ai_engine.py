import google.generativeai as genai
import logging
import json

logger = logging.getLogger("BG_STAR_PRO_AIEngine")

class GeminiAIEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Initialize Gemini API
        genai.configure(api_key=self.api_key)
        
        # Using gemini-1.5-flash for maximum speed and cost efficiency in production
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    def evaluate_signal(self, coin: str, tech_data: dict, news_data: dict) -> dict:
        """
        Stage 4 Execution: Analyzes Technical and News data to give final confirmation.
        Returns: strict JSON format containing action, confidence, and reason.
        """
        logger.info(f"🧠 Gemini API Triggered for {coin}. Analyzing Technical + News data...")
        
        # Emergency Fallback Response
        fallback_response = {
            "action": "WAIT", 
            "confidence": 0, 
            "reason": "AI evaluation failed or API unavailable. Falling back to Technical Engine."
        }

        # Constructing a strictly controlled prompt (Zero-Hallucination Prompting)
        prompt = f"""
        You are an institutional Quant Trading AI for 'BG STAR PRO'.
        Your job is to evaluate the following market setup and provide a final decision.
        
        Asset: {coin}
        
        [Technical Data]
        Trend Direction: {tech_data.get('direction')}
        Smart Triggers Active: {', '.join(tech_data.get('trigger_reasons', []))}
        Technical Base Score: {tech_data.get('technical_score')}/100
        
        [News Data]
        Macro Sentiment: {news_data.get('sentiment')}
        News Context: {news_data.get('reason')}
        
        Evaluate the confluence between Technicals and News. 
        You MUST respond ONLY with a valid JSON object. Do not include markdown blocks, greetings, or extra text.
        
        JSON Format Required:
        {{
            "action": "BUY",  // Must be exactly "BUY", "SELL", or "WAIT"
            "confidence": 95, // Integer between 0 and 100
            "reason": "Short one-sentence explanation of your confluence logic."
        }}
        """

        try:
            # Setting a safety config and lower temperature for strict analytical output
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Low temp for deterministic logic
                    response_mime_type="application/json" # Forces JSON output
                )
            )

            # Parsing the JSON response
            ai_result = json.loads(response.text)
            
            # Validation matching Blueprint specs
            action = ai_result.get("action", "WAIT").upper()
            if action not in ["BUY", "SELL", "WAIT"]:
                action = "WAIT"

            return {
                "action": action,
                "confidence": int(ai_result.get("confidence", 0)),
                "reason": ai_result.get("reason", "No reason provided.")
            }

        except json.JSONDecodeError:
            logger.error("🛑 Gemini returned malformed JSON. Switching to Fallback.")
            return fallback_response
        except Exception as e:
            # Handles API Limits, Quota Exhausted, Network Timeouts, etc.
            logger.error(f"🛑 Gemini API Error: {e}. Switching to Fallback.")
            return fallback_response

# Usage in Main App Loop (Blueprint Logic):
# if tech_data["is_triggered"] and news_data["sentiment"] in ["BULLISH", "BEARISH"]:
#     ai_data = ai_engine.evaluate_signal(coin, tech_data, news_data)
#     if ai_data["action"] in ["BUY", "SELL"]:
#         # STRONG SIGNAL 🟢 Generate Final Telegram Alert
