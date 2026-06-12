from llm_client import generate_sql

question = "List all employees in the Sales department."

sql = generate_sql(question)

print("Question:")
print(question)

print("\nGenerated SQL:")
print(sql)