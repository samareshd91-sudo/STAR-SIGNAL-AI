import logging
import os
import re


logger = logging.getLogger("BG_STAR_PRO_AI")


class GeminiAIEngine:

    def __init__(self, api_key: str):
        self.api_key = api_key

        # Current stable model can be overridden from Render.
        self.model_name = os.getenv(
            "GEMINI_MODEL_NAME",
            "gemini-3.6-flash",
        )

        self.client = None
        self.legacy_model = None
        self.mode = "NONE"

        if not self.api_key:
            logger.warning(
                "Gemini API key is missing."
            )
            return

        # ------------------------------------------------------
        # Preferred: new google-genai SDK
        # ------------------------------------------------------
        try:
            from google import genai

            self.client = genai.Client(
                api_key=self.api_key
            )

            self.mode = "NEW"

            logger.info(
                "Gemini initialized using google-genai: %s",
                self.model_name,
            )

            return

        except Exception as exc:
            logger.warning(
                "New google-genai SDK unavailable: %s",
                exc,
            )

        # ------------------------------------------------------
        # Compatibility fallback for existing deployments
        # ------------------------------------------------------
        try:
            import google.generativeai as genai

            genai.configure(
                api_key=self.api_key
            )

            self.legacy_model = (
                genai.GenerativeModel(
                    self.model_name
                )
            )

            self.mode = "LEGACY"

            logger.warning(
                "Using legacy google-generativeai "
                "compatibility mode."
            )

        except Exception as exc:
            logger.error(
                "Gemini initialization failed: %s",
                exc,
            )

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def evaluate_signal(
        self,
        coin: str,
        tech_data: dict,
        news_data: dict,
    ) -> dict:

        if self.mode == "NONE":
            return {
                "action": "WAIT",
                "confidence": 0,
                "reason": "Gemini unavailable.",
                "status": "UNAVAILABLE",
            }

        direction = tech_data.get(
            "direction",
            "NEUTRAL",
        )

        technical_score = tech_data.get(
            "technical_score",
            0,
        )

        features = tech_data.get(
            "features",
            {},
        )

        expected_action = (
            "BUY"
            if direction == "BULLISH"
            else "SELL"
        )

        prompt = self._build_prompt(
            coin=coin,
            expected_action=expected_action,
            technical_score=technical_score,
            features=features,
            news_data=news_data,
        )

        try:
            logger.info(
                "Gemini confirmation started: %s",
                coin,
            )

            if self.mode == "NEW":
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )

                text = getattr(
                    response,
                    "text",
                    "",
                )

            else:
                response = self.legacy_model.generate_content(
                    prompt
                )

                text = getattr(
                    response,
                    "text",
                    "",
                )

            if not text:
                return {
                    "action": "WAIT",
                    "confidence": 0,
                    "reason": "Empty Gemini response.",
                    "status": "ERROR",
                }

            parsed = self._parse_response(
                text
            )

            if parsed["action"] not in {
                "BUY",
                "SELL",
                "WAIT",
            }:
                return {
                    "action": "WAIT",
                    "confidence": 0,
                    "reason": "Invalid Gemini action.",
                    "status": "ERROR",
                }

            return {
                "action": parsed["action"],
                "confidence": parsed["confidence"],
                "reason": parsed["reason"][:250],
                "status": "SUCCESS",
            }

        except Exception as exc:
            logger.error(
                "Gemini API error for %s: %s",
                coin,
                exc,
            )

            return {
                "action": "WAIT",
                "confidence": 0,
                "reason": str(exc)[:200],
                "status": "ERROR",
            }

    # ==========================================================
    # PROMPT
    # ==========================================================

    @staticmethod
    def _build_prompt(
        coin,
        expected_action,
        technical_score,
        features,
        news_data,
    ):

        news_sentiment = news_data.get(
            "sentiment",
            "NEUTRAL",
        )

        news_context = news_data.get(
            "context",
            "",
        )

        prompt = f"""
You are the final confirmation layer for a conservative
crypto technical signal engine.

You are NOT allowed to create a trade just because you
like the market.

Expected technical direction:
{expected_action}

Asset:
{coin}

Technical score:
{technical_score}/100

1H direction:
{features.get("one_hour_direction")}

4H direction:
{features.get("four_hour_direction")}

Structure:
{features.get("structure_direction")}

EMA:
{features.get("ema_direction")}

ADX:
{features.get("adx_value")}

Pressure:
{features.get("pressure_direction")}

Displacement ratio:
{features.get("displacement_ratio")}

Liquidity:
{features.get("liquidity_direction")}

OB/FVG:
{features.get("ob_fvg_direction")}

Two-candle confirmation:
{features.get("candle_confirmation")}

News sentiment:
{news_sentiment}

News:
{news_context}

STRICT RULES:

1. Do not invent missing technical evidence.
2. Do not override strong technical contradictions.
3. If the technical direction and market structure disagree,
   return WAIT.
4. If HTF alignment is unclear, return WAIT.
5. If the setup looks like a whipsaw or weak reversal,
   return WAIT.
6. Only return BUY if the expected technical direction is BUY.
7. Only return SELL if the expected technical direction is SELL.
8. Otherwise return WAIT.
9. Confidence must represent your actual confidence.
10. Do not use 90 by default.

Return EXACTLY these three lines:

ACTION=BUY
CONFIDENCE=0
REASON=short reason

OR

ACTION=SELL
CONFIDENCE=0
REASON=short reason

OR

ACTION=WAIT
CONFIDENCE=0
REASON=short reason
"""

        return prompt

    # ==========================================================
    # PARSER
    # ==========================================================

    @staticmethod
    def _parse_response(
        text: str,
    ) -> dict:

        action_match = re.search(
            r"\bACTION\s*=\s*(BUY|SELL|WAIT)\b",
            text.upper(),
        )

        confidence_match = re.search(
            r"\bCONFIDENCE\s*=\s*(\d{1,3})\b",
            text.upper(),
        )

        reason_match = re.search(
            r"\bREASON\s*=\s*(.+)",
            text,
            re.IGNORECASE,
        )

        action = (
            action_match.group(1)
            if action_match
            else "WAIT"
        )

        confidence = 0

        if confidence_match:
            confidence = min(
                100,
                max(
                    0,
                    int(
                        confidence_match.group(1)
                    ),
                ),
            )

        reason = (
            reason_match.group(1).strip()
            if reason_match
            else text.strip()
        )

        return {
            "action": action,
            "confidence": confidence,
            "reason": reason,
        }
