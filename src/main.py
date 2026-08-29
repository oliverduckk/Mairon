print("Mairon v0.1 starting...")
input_name = input("What is your name? ")
print(f"Good evening, {input_name}.")

while True:
    user_input = input("You: ").strip().lower()

    if user_input == "exit":
        print("Mairon: Shutting down.")
        break

    else:
        print("Mairon: I don't understand that command yet.\n")
