from typing import List, Union

import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingEngine:
    def __init__(self, model_name: str):
        print(f"Loading embedding model: {model_name}...")
        self.model = SentenceTransformer(model_name)
        print("Model loaded.")

    def encode(self, texts: Union[str, List[str]]) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        return np.asarray(self.model.encode(texts, convert_to_tensor=False))

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        dot = np.dot(vec1, vec2)
        norm = np.linalg.norm(vec1) * np.linalg.norm(vec2)
        return float(dot / (norm + 1e-8))
