#!/usr/bin/env python3
"""
Test: Ellenőrizzük, hogy az 5000kg-os küszöb javítás működne-e
"""

# Szimuláljuk a talált feltöltéseket a korábbi futásból
refills = [
    ("2025-11-08 12:00", 5275),  # Ez a legnagyobb
    ("2025-11-08 18:00", 3373),
    ("2025-11-11 06:00", 3485),
    ("2025-11-11 12:00", 4928),
    ("2025-11-15 12:00", 3702),
    ("2025-11-15 18:00", 4727),
    ("2025-11-18 12:00", 4343),
]

print("🎯 Feltöltés detektálás teszt")
print("=" * 80)
print("\nRÉGI küszöb (10000 kg):")
print("-" * 40)
old_threshold = 10000
old_found = [r for r in refills if r[1] > old_threshold]
if old_found:
    for date, weight in old_found:
        print(f"✅ {date}: +{weight} kg")
else:
    print("❌ Nincs találat!")

print("\nÚJ küszöb (5000 kg):")
print("-" * 40)
new_threshold = 5000
new_found = [r for r in refills if r[1] > new_threshold]
if new_found:
    for date, weight in new_found:
        print(f"✅ {date}: +{weight} kg")
    print(f"\n🎉 ELSŐ ciklus kezdő feltöltés: {new_found[0][0]} (+{new_found[0][1]} kg)")
else:
    print("❌ Nincs találat!")

print("\n" + "=" * 80)
print("Következtetés:")
if len(old_found) == 0 and len(new_found) > 0:
    print("✅ A javítás MŰKÖDIK! Az 5000kg küszöb megtalálja a ciklus kezdetet.")
else:
    print("❓ További elemzés szükséges.")
