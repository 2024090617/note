from llm_service.thesis.agent import ThesisAgent

agent = ThesisAgent()

# Check available skills
print(agent.list_available_skills())

# Write section using doc-coauthoring workflow
section = agent.write_section_with_skill(
    section_id="1.1",
    section_title="研究背景",
    target_words=800
)

# Or use full interactive workflow
section = agent.interactive_write_section("1.2", "研究意义")

# Export with docx skill enhancements
agent.export_docx_with_skill("thesis.docx", author="张三")