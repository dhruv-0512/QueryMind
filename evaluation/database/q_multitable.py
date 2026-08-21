# Multi-table benchmark questions using the aviation schema from db_engine.py
# Tables: airlines, airports, aircraft, flights, passengers, bookings
# No new data — these questions run against the same SQLite DB set up in evaluate.py

QUESTIONS = [
    # ── 2-TABLE INNER JOIN ────────────────────────────────────────────────────
    {"q": "List all flights along with their airline name.",
     "sql": "SELECT f.flight_number, al.airline_name, f.status FROM flights f INNER JOIN airlines al ON f.airline_id = al.airline_id ORDER BY f.flight_id;",
     "difficulty": "easy", "category": "JOIN", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Show flight numbers and the city each flight departs from.",
     "sql": "SELECT f.flight_number, ap.city AS origin_city FROM flights f INNER JOIN airports ap ON f.origin_airport_id = ap.airport_id;",
     "difficulty": "easy", "category": "JOIN", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Show flight numbers and the city each flight arrives at.",
     "sql": "SELECT f.flight_number, ap.city AS destination_city FROM flights f INNER JOIN airports ap ON f.destination_airport_id = ap.airport_id;",
     "difficulty": "easy", "category": "JOIN", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "List all bookings with passenger first and last name.",
     "sql": "SELECT b.booking_id, p.first_name, p.last_name, b.seat_class, b.fare_amount, b.booking_status FROM bookings b INNER JOIN passengers p ON b.passenger_id = p.passenger_id;",
     "difficulty": "easy", "category": "JOIN", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Show each aircraft model alongside the airline that owns it.",
     "sql": "SELECT ac.model, al.airline_name FROM aircraft ac INNER JOIN airlines al ON ac.airline_id = al.airline_id ORDER BY al.airline_name;",
     "difficulty": "easy", "category": "JOIN", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "How many bookings does each passenger have?",
     "sql": "SELECT p.first_name, p.last_name, COUNT(b.booking_id) AS booking_count FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id GROUP BY p.passenger_id ORDER BY booking_count DESC;",
     "difficulty": "easy", "category": "JOIN + GROUP BY", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "What is the total revenue per airline from confirmed bookings?",
     "sql": "SELECT al.airline_name, ROUND(SUM(b.fare_amount), 2) AS total_revenue FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY al.airline_id ORDER BY total_revenue DESC;",
     "difficulty": "medium", "category": "JOIN + GROUP BY", "join_count": 2, "join_type": "INNER JOIN"},

    # ── LEFT JOIN ─────────────────────────────────────────────────────────────
    {"q": "List all passengers including those who have never made a booking.",
     "sql": "SELECT p.first_name, p.last_name, b.booking_id FROM passengers p LEFT JOIN bookings b ON p.passenger_id = b.passenger_id;",
     "difficulty": "easy", "category": "LEFT JOIN", "join_count": 1, "join_type": "LEFT JOIN"},

    {"q": "Which passengers have never made a booking?",
     "sql": "SELECT p.first_name, p.last_name FROM passengers p LEFT JOIN bookings b ON p.passenger_id = b.passenger_id WHERE b.booking_id IS NULL;",
     "difficulty": "easy", "category": "LEFT JOIN", "join_count": 1, "join_type": "LEFT JOIN"},

    {"q": "List all flights including those with no bookings.",
     "sql": "SELECT f.flight_number, f.status, COUNT(b.booking_id) AS booking_count FROM flights f LEFT JOIN bookings b ON f.flight_id = b.flight_id GROUP BY f.flight_id ORDER BY booking_count DESC;",
     "difficulty": "medium", "category": "LEFT JOIN", "join_count": 1, "join_type": "LEFT JOIN"},

    {"q": "Which flights have zero bookings of any status?",
     "sql": "SELECT f.flight_number, f.status FROM flights f LEFT JOIN bookings b ON f.flight_id = b.flight_id WHERE b.booking_id IS NULL;",
     "difficulty": "medium", "category": "LEFT JOIN", "join_count": 1, "join_type": "LEFT JOIN"},

    {"q": "List all airlines and how many aircraft they own, including airlines with no aircraft.",
     "sql": "SELECT al.airline_name, COUNT(ac.aircraft_id) AS aircraft_count FROM airlines al LEFT JOIN aircraft ac ON al.airline_id = ac.airline_id GROUP BY al.airline_id ORDER BY aircraft_count DESC;",
     "difficulty": "medium", "category": "LEFT JOIN", "join_count": 1, "join_type": "LEFT JOIN"},

    # ── 3-TABLE INNER JOIN ────────────────────────────────────────────────────
    {"q": "List all confirmed bookings with passenger name and their flight number.",
     "sql": "SELECT p.first_name, p.last_name, f.flight_number, b.seat_class, b.fare_amount FROM bookings b INNER JOIN passengers p ON b.passenger_id = p.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id WHERE b.booking_status = 'Confirmed' ORDER BY b.fare_amount DESC;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Which passenger flew on which airline?",
     "sql": "SELECT DISTINCT p.first_name, p.last_name, al.airline_name FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id INNER JOIN airlines al ON f.airline_id = al.airline_id ORDER BY al.airline_name;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 3, "join_type": "INNER JOIN"},

    {"q": "Show the total spending per passenger across all their confirmed bookings.",
     "sql": "SELECT p.first_name, p.last_name, ROUND(SUM(b.fare_amount), 2) AS total_spent FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY p.passenger_id ORDER BY total_spent DESC;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Which airline had the most confirmed bookings?",
     "sql": "SELECT al.airline_name, COUNT(*) AS confirmed_count FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY al.airline_id ORDER BY confirmed_count DESC LIMIT 1;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "List all flights with origin city and destination city.",
     "sql": "SELECT f.flight_number, o.city AS origin, d.city AS destination, f.status FROM flights f INNER JOIN airports o ON f.origin_airport_id = o.airport_id INNER JOIN airports d ON f.destination_airport_id = d.airport_id;",
     "difficulty": "medium", "category": "self-like JOIN (same table twice)", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Show flights with their aircraft model and operating airline.",
     "sql": "SELECT f.flight_number, ac.model AS aircraft_model, al.airline_name FROM flights f INNER JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id INNER JOIN airlines al ON f.airline_id = al.airline_id ORDER BY f.flight_number;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    # ── 3-TABLE JOIN + GROUP BY ───────────────────────────────────────────────
    {"q": "How many distinct passengers did each airline fly?",
     "sql": "SELECT al.airline_name, COUNT(DISTINCT b.passenger_id) AS unique_passengers FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id GROUP BY al.airline_id ORDER BY unique_passengers DESC;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "What is the average fare amount per airline for confirmed bookings?",
     "sql": "SELECT al.airline_name, ROUND(AVG(b.fare_amount), 2) AS avg_fare FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY al.airline_id ORDER BY avg_fare DESC;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "List the number of flights that departed from each country.",
     "sql": "SELECT ap.country, COUNT(f.flight_id) AS departures FROM airports ap INNER JOIN flights f ON ap.airport_id = f.origin_airport_id GROUP BY ap.country ORDER BY departures DESC;",
     "difficulty": "easy", "category": "JOIN + GROUP BY", "join_count": 1, "join_type": "INNER JOIN"},

    # ── JOIN + HAVING ─────────────────────────────────────────────────────────
    {"q": "Which passengers have more than one confirmed booking?",
     "sql": "SELECT p.first_name, p.last_name, COUNT(*) AS confirmed_count FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id WHERE b.booking_status = 'Confirmed' GROUP BY p.passenger_id HAVING COUNT(*) > 1 ORDER BY confirmed_count DESC;",
     "difficulty": "medium", "category": "HAVING", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Which airlines have flown more than 1 distinct aircraft model?",
     "sql": "SELECT al.airline_name, COUNT(DISTINCT ac.model) AS distinct_models FROM airlines al INNER JOIN aircraft ac ON al.airline_id = ac.airline_id GROUP BY al.airline_id HAVING COUNT(DISTINCT ac.model) > 1;",
     "difficulty": "medium", "category": "HAVING", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Which passengers have spent more than $1000 on confirmed bookings?",
     "sql": "SELECT p.first_name, p.last_name, ROUND(SUM(b.fare_amount), 2) AS total_spent FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id WHERE b.booking_status = 'Confirmed' GROUP BY p.passenger_id HAVING SUM(b.fare_amount) > 1000 ORDER BY total_spent DESC;",
     "difficulty": "medium", "category": "HAVING", "join_count": 1, "join_type": "INNER JOIN"},

    # ── JOIN + ORDER BY / LIMIT ───────────────────────────────────────────────
    {"q": "Who are the top 3 highest-spending passengers?",
     "sql": "SELECT p.first_name, p.last_name, ROUND(SUM(b.fare_amount), 2) AS total_spent FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id WHERE b.booking_status = 'Confirmed' GROUP BY p.passenger_id ORDER BY total_spent DESC LIMIT 3;",
     "difficulty": "medium", "category": "JOIN + ORDER BY/LIMIT", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Show the 5 most expensive bookings with passenger name and flight number.",
     "sql": "SELECT p.first_name, p.last_name, f.flight_number, b.fare_amount, b.seat_class FROM bookings b INNER JOIN passengers p ON b.passenger_id = p.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id ORDER BY b.fare_amount DESC LIMIT 5;",
     "difficulty": "medium", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Which flight had the highest total revenue from all booking statuses?",
     "sql": "SELECT f.flight_number, ROUND(SUM(b.fare_amount), 2) AS flight_revenue FROM flights f INNER JOIN bookings b ON f.flight_id = b.flight_id GROUP BY f.flight_id ORDER BY flight_revenue DESC LIMIT 1;",
     "difficulty": "medium", "category": "JOIN + ORDER BY/LIMIT", "join_count": 1, "join_type": "INNER JOIN"},

    # ── JOIN + DISTINCT ───────────────────────────────────────────────────────
    {"q": "List distinct countries that have passengers who have flown with SkyBridge Airlines.",
     "sql": "SELECT DISTINCT p.nationality FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id INNER JOIN airlines al ON f.airline_id = al.airline_id WHERE al.airline_name = 'SkyBridge Airlines';",
     "difficulty": "hard", "category": "DISTINCT + multiple joins", "join_count": 3, "join_type": "INNER JOIN"},

    {"q": "List the distinct seat classes booked for each airline.",
     "sql": "SELECT DISTINCT al.airline_name, b.seat_class FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id ORDER BY al.airline_name, b.seat_class;",
     "difficulty": "medium", "category": "DISTINCT + multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    # ── MANY-TO-MANY (passengers <-> flights via bookings) ────────────────────
    {"q": "Which passengers have booked flights on more than one airline?",
     "sql": "SELECT p.first_name, p.last_name, COUNT(DISTINCT f.airline_id) AS num_airlines FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id GROUP BY p.passenger_id HAVING COUNT(DISTINCT f.airline_id) > 1;",
     "difficulty": "hard", "category": "HAVING", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "How many passengers has each flight carried (confirmed bookings only)?",
     "sql": "SELECT f.flight_number, COUNT(b.passenger_id) AS passenger_count FROM flights f INNER JOIN bookings b ON f.flight_id = b.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY f.flight_id ORDER BY passenger_count DESC;",
     "difficulty": "easy", "category": "JOIN + GROUP BY", "join_count": 1, "join_type": "INNER JOIN"},

    # ── CROSS-TABLE SUBQUERIES ────────────────────────────────────────────────
    {"q": "Find passengers who have only ever flown in Business or First class.",
     "sql": "SELECT DISTINCT p.first_name, p.last_name FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id WHERE p.passenger_id NOT IN (SELECT passenger_id FROM bookings WHERE seat_class = 'Economy');",
     "difficulty": "hard", "category": "nested queries", "join_count": 1, "join_type": "INNER JOIN"},

    {"q": "Which airlines carry passengers whose total spending exceeds $2000?",
     "sql": "SELECT DISTINCT al.airline_name FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id WHERE b.passenger_id IN (SELECT passenger_id FROM bookings WHERE booking_status = 'Confirmed' GROUP BY passenger_id HAVING SUM(fare_amount) > 2000);",
     "difficulty": "hard", "category": "nested queries", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "List flights that depart from airports serving more than 1 flight.",
     "sql": "SELECT f.flight_number, ap.city FROM flights f INNER JOIN airports ap ON f.origin_airport_id = ap.airport_id WHERE f.origin_airport_id IN (SELECT origin_airport_id FROM flights GROUP BY origin_airport_id HAVING COUNT(*) > 1);",
     "difficulty": "hard", "category": "nested queries", "join_count": 1, "join_type": "INNER JOIN"},

    # ── CTE-BASED ─────────────────────────────────────────────────────────────
    {"q": "Using a CTE, find the highest-spending passenger per airline.",
     "sql": """WITH passenger_spending AS (
    SELECT f.airline_id, b.passenger_id, SUM(b.fare_amount) AS total_spent
    FROM bookings b
    INNER JOIN flights f ON b.flight_id = f.flight_id
    WHERE b.booking_status = 'Confirmed'
    GROUP BY f.airline_id, b.passenger_id
)
SELECT al.airline_name, p.first_name, p.last_name, ps.total_spent
FROM passenger_spending ps
INNER JOIN airlines al ON ps.airline_id = al.airline_id
INNER JOIN passengers p ON ps.passenger_id = p.passenger_id
WHERE ps.total_spent = (
    SELECT MAX(total_spent) FROM passenger_spending ps2 WHERE ps2.airline_id = ps.airline_id
)
ORDER BY ps.total_spent DESC;""",
     "difficulty": "hard", "category": "CTE", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Using a CTE, rank airlines by their average booking fare.",
     "sql": """WITH airline_avg AS (
    SELECT al.airline_id, al.airline_name, AVG(b.fare_amount) AS avg_fare
    FROM airlines al
    INNER JOIN flights f ON al.airline_id = f.airline_id
    INNER JOIN bookings b ON f.flight_id = b.flight_id
    WHERE b.booking_status = 'Confirmed'
    GROUP BY al.airline_id, al.airline_name
)
SELECT airline_name, ROUND(avg_fare, 2) AS avg_fare
FROM airline_avg
ORDER BY avg_fare DESC;""",
     "difficulty": "hard", "category": "CTE", "join_count": 2, "join_type": "INNER JOIN"},

    # ── SAME TABLE TWICE (simulated self-join via airports) ───────────────────
    {"q": "For each flight, show both the origin and destination airport country.",
     "sql": "SELECT f.flight_number, o.country AS origin_country, d.country AS destination_country FROM flights f INNER JOIN airports o ON f.origin_airport_id = o.airport_id INNER JOIN airports d ON f.destination_airport_id = d.airport_id;",
     "difficulty": "medium", "category": "self-like JOIN", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Which flights are international (origin and destination in different countries)?",
     "sql": "SELECT f.flight_number, o.country AS origin_country, d.country AS destination_country FROM flights f INNER JOIN airports o ON f.origin_airport_id = o.airport_id INNER JOIN airports d ON f.destination_airport_id = d.airport_id WHERE o.country != d.country;",
     "difficulty": "medium", "category": "self-like JOIN", "join_count": 2, "join_type": "INNER JOIN"},

    # ── AGGREGATION ACROSS 4 TABLES ───────────────────────────────────────────
    {"q": "What is the total capacity used (confirmed bookings) vs available capacity per flight?",
     "sql": "SELECT f.flight_number, ac.capacity AS total_capacity, COUNT(b.booking_id) AS confirmed_pax, ROUND(100.0 * COUNT(b.booking_id) / ac.capacity, 1) AS load_factor_pct FROM flights f INNER JOIN aircraft ac ON f.aircraft_id = ac.aircraft_id LEFT JOIN bookings b ON f.flight_id = b.flight_id AND b.booking_status = 'Confirmed' GROUP BY f.flight_id, ac.capacity ORDER BY load_factor_pct DESC;",
     "difficulty": "hard", "category": "multiple joins", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "Which nationality spent the most on Business class across all airlines?",
     "sql": "SELECT p.nationality, ROUND(SUM(b.fare_amount), 2) AS total_business_spend FROM passengers p INNER JOIN bookings b ON p.passenger_id = b.passenger_id INNER JOIN flights f ON b.flight_id = f.flight_id INNER JOIN airlines al ON f.airline_id = al.airline_id WHERE b.seat_class = 'Business' AND b.booking_status = 'Confirmed' GROUP BY p.nationality ORDER BY total_business_spend DESC LIMIT 1;",
     "difficulty": "hard", "category": "multiple joins", "join_count": 3, "join_type": "INNER JOIN"},

    {"q": "Show the average aircraft manufacture year per airline along with their total fleet capacity.",
     "sql": "SELECT al.airline_name, ROUND(AVG(ac.manufacture_year), 1) AS avg_year, SUM(ac.capacity) AS total_capacity FROM airlines al INNER JOIN aircraft ac ON al.airline_id = ac.airline_id GROUP BY al.airline_id ORDER BY avg_year DESC;",
     "difficulty": "medium", "category": "JOIN + GROUP BY", "join_count": 1, "join_type": "INNER JOIN"},

    # ── DATE-BASED CROSS-TABLE ────────────────────────────────────────────────
    {"q": "How many confirmed bookings were made per month for each airline?",
     "sql": "SELECT al.airline_name, strftime('%Y-%m', b.booking_date) AS month, COUNT(*) AS bookings FROM airlines al INNER JOIN flights f ON al.airline_id = f.airline_id INNER JOIN bookings b ON f.flight_id = b.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY al.airline_id, month ORDER BY al.airline_name, month;",
     "difficulty": "hard", "category": "date functions", "join_count": 2, "join_type": "INNER JOIN"},

    {"q": "What is the average time between booking date and departure date per seat class?",
     "sql": "SELECT b.seat_class, ROUND(AVG(julianday(f.departure_time) - julianday(b.booking_date)), 1) AS avg_days_in_advance FROM bookings b INNER JOIN flights f ON b.flight_id = f.flight_id WHERE b.booking_status = 'Confirmed' GROUP BY b.seat_class ORDER BY avg_days_in_advance DESC;",
     "difficulty": "hard", "category": "date functions", "join_count": 1, "join_type": "INNER JOIN"},
]
