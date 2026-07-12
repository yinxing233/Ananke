from ananke.config import Config
from ananke.embedding import EmbeddingEngine
from ananke.llm_client import LLMClient
from ananke.logger import EventLogger
from ananke.memory_store import MemoryStore
from ananke.pipeline import MemoryPipeline


def main() -> None:
    pipeline = MemoryPipeline(MemoryStore(), EmbeddingEngine(Config.EMBEDDING_MODEL), LLMClient(), EventLogger())
    print("Ananke memory MVP. 输入 exit 退出。")
    while (user_input := input("> ").strip()) != "exit":
        if not user_input: continue
        result = pipeline.process(user_input)
        print(f"写入 {len(result['written'])} 条；迁入中层 {len(result['consolidated'])} 条；迁入慢层 {len(result['core'])} 条。")


if __name__ == "__main__": main()
