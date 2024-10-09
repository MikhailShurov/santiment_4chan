import requests
import matplotlib.pyplot as plt

response = requests.get('https://a.4cdn.org/biz/archive.json')
numbers = response.json()[20:]

differences = [numbers[i] - numbers[i - 1] for i in range(1, len(numbers))]

plt.figure(figsize=(10, 6))
plt.plot(differences, marker='o', linestyle='-', color='b')
plt.title('Differences Between Subsequent Numbers')
plt.xlabel('Ids')
plt.ylabel('Difference')
plt.grid(True)
plt.show()
