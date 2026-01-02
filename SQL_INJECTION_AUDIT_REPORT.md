# SQL Injection Vulnerability Audit Report
## Flask Restaurant Reservation System
**Date:** 2026-01-02
**Status:** CONFIDENTIAL - Production Security Audit

---

## Executive Summary

✅ **GOOD NEWS:** Your application is **largely secure** against SQL injection attacks. Most queries use proper parameterized statements with `?` placeholders.

⚠️ **1 MINOR ISSUE FOUND:** One location uses unsafe string interpolation, though it has partial protection.

---

## Vulnerability Details

### ⚠️ VULNERABILITY #1: Unsafe LIMIT Clause (LOW SEVERITY)

**File:** `app.py`
**Lines:** 1456-1464
**Endpoint:** `/api/admin/raw`
**Severity:** LOW (Has partial protection via int() conversion)

#### Current Code:
```python
limit = request.args.get('limit', '100')

with get_db() as conn:
    cursor = conn.cursor()

    if limit == 'all':
        query = 'SELECT * FROM reservations ORDER BY id DESC'
    else:
        query = f'SELECT * FROM reservations ORDER BY id DESC LIMIT {int(limit)}'  # ⚠️ UNSAFE

    cursor.execute(query)
```

#### Why It's Vulnerable:
- Uses f-string interpolation to insert the `limit` value directly into the SQL query
- While `int()` conversion provides some protection (will throw ValueError on non-numeric input), this is NOT the proper way to prevent SQL injection
- Not following SQLite best practices for parameterized queries

#### How to Fix:
Replace the f-string with a parameterized query:

```python
limit = request.args.get('limit', '100')

with get_db() as conn:
    cursor = conn.cursor()

    if limit == 'all':
        query = 'SELECT * FROM reservations ORDER BY id DESC'
        cursor.execute(query)
    else:
        query = 'SELECT * FROM reservations ORDER BY id DESC LIMIT ?'
        cursor.execute(query, (int(limit),))  # ✅ SAFE - Parameterized

    reservations = [dict(row) for row in cursor.fetchall()]
```

---

## Additional Security Observations

### ✅ Generally Safe Pattern (BUT Could Be Improved)

**File:** `app.py`
**Lines:** 1384-1439
**Endpoint:** `/api/admin/reservations`

#### Current Code:
```python
sort = request.args.get('sort', 'fecha')

# ... building where_clauses and params ...

# Determine sort order
valid_sorts = ['fecha', 'created_at', 'cancelled_at', 'personas', 'hora']
if sort not in valid_sorts:
    sort = 'fecha'

query = f'''
    SELECT * FROM reservations
    WHERE {where_sql}
    ORDER BY {sort} DESC, hora
'''

cursor.execute(query, params)
```

#### Why It's Safe (for now):
- The `sort` parameter is validated against a **whitelist** of allowed column names
- The WHERE clause uses parameterized queries with the `params` list
- No direct user input reaches the SQL query without validation

#### Why It Could Be Better:
- Using f-strings for SQL construction is a **code smell** that could lead to future vulnerabilities if someone modifies the code
- If the whitelist is removed or bypassed in future edits, this becomes immediately vulnerable

#### Recommended Improvement (Optional):
While this is technically safe due to the whitelist, consider using a more explicit approach:

```python
# Map of allowed sort values to actual column names
SORT_COLUMNS = {
    'fecha': 'fecha',
    'created_at': 'created_at',
    'cancelled_at': 'cancelled_at',
    'personas': 'personas',
    'hora': 'hora'
}

sort = request.args.get('sort', 'fecha')
sort_column = SORT_COLUMNS.get(sort, 'fecha')  # Default to fecha if invalid

query = f'''
    SELECT * FROM reservations
    WHERE {where_sql}
    ORDER BY {sort_column} DESC, hora
'''
```

This makes the whitelist more explicit and maintainable.

---

## Files Audited

### ✅ app.py - 27 SQL query locations
- ✅ 26 locations use proper parameterized queries
- ⚠️ 1 location uses unsafe string interpolation (line 1464)

### ✅ discord_bot.py - 15 SQL query locations
- ✅ All queries use proper parameterized queries or hardcoded SQL
- ✅ No vulnerabilities found

### ✅ delete_old_reservations.py - 5 SQL query locations
- ✅ All queries use hardcoded SQL with SQLite date functions
- ✅ No user input, no vulnerabilities

---

## Secure Coding Patterns Found ✅

Your code demonstrates excellent security practices in most places:

1. **Parameterized Queries:** Almost all queries use `?` placeholders
   ```python
   cursor.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,))
   ```

2. **Input Validation:** Phone number cleaning, date validation, etc.
   ```python
   clean_phone = clean_phone_number(data['telefono'])
   ```

3. **No Raw String Concatenation:** No dangerous patterns like:
   ```python
   # ❌ DANGEROUS (not found in your code)
   query = "SELECT * FROM users WHERE username = '" + username + "'"
   ```

---

## Recommendations

### 🔴 IMMEDIATE ACTION REQUIRED

**Fix the LIMIT clause in app.py line 1464:**
- Replace f-string interpolation with parameterized query
- See "How to Fix" section above

### 🟡 OPTIONAL IMPROVEMENTS

1. **Whitelist Pattern Documentation:**
   - Add comments explaining why the whitelist exists in `/api/admin/reservations`
   - Consider making the whitelist a module-level constant for clarity

2. **Code Review Process:**
   - Add a linting rule to flag f-strings in SQL queries
   - Consider using an ORM like SQLAlchemy for automatic parameterization

3. **Security Testing:**
   - Add automated SQL injection tests to your test suite
   - Use tools like `sqlmap` to test your endpoints

---

## Testing the Vulnerability

To verify the LOW severity of the current vulnerability in `/api/admin/raw`:

### Test 1: Bypass Attempt (Will Fail)
```bash
curl "http://localhost:5000/api/admin/raw?limit=100%20OR%201=1"
# Expected: ValueError exception (int() will fail)
```

### Test 2: After Fix (Should Work)
```bash
curl "http://localhost:5000/api/admin/raw?limit=50"
# Expected: Returns 50 reservations safely
```

---

## Conclusion

Your Flask application is **well-protected** against SQL injection attacks. The single vulnerability found has low severity due to the `int()` conversion providing partial protection.

**Bottom Line:**
- Fix the one issue in `app.py:1464` by using parameterized queries
- Your production system is not at high risk, but the fix should be implemented
- Overall security posture: **GOOD** ✅

---

## Appendix: Safe Query Examples from Your Code

Here are examples of proper parameterized queries from your codebase (use these as templates):

```python
# ✅ Example 1: Simple SELECT with parameter
cursor.execute('''
    SELECT * FROM reservations
    WHERE confirmation_token = ?
    AND cancelled = 0
''', (token,))

# ✅ Example 2: INSERT with multiple parameters
cursor.execute('''
    INSERT INTO reservations
    (nombre, telefono, personas, fecha, hora, user_confirmed, restaurant_confirmed, confirmation_token, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (nombre, telefono, personas, fecha, hora, 0, 1, token, notes))

# ✅ Example 3: UPDATE with parameters
cursor.execute('''
    UPDATE reservations
    SET cancelled = 1, cancelled_at = CURRENT_TIMESTAMP, cancelled_by = ?
    WHERE id = ?
''', ('admin', reservation_id))

# ✅ Example 4: DELETE with parameters
cursor.execute('''
    DELETE FROM blocked_hours
    WHERE fecha = ? AND hora = ?
''', (fecha, hora))
```

---

**Report prepared by:** Claude Code SQL Injection Audit
**Classification:** CONFIDENTIAL
**Distribution:** Internal use only - Do not merge to public repositories
