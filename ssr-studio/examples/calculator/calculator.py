"""
A simple calculator module with various operations.
This serves as a realistic target for bug injection/repair demos.
"""

from typing import List, Union, Optional
from decimal import Decimal, InvalidOperation
import math


class CalculatorError(Exception):
    """Base exception for calculator errors."""
    pass


class DivisionByZeroError(CalculatorError):
    """Raised when attempting to divide by zero."""
    pass


class InvalidInputError(CalculatorError):
    """Raised when input is invalid."""
    pass


class Calculator:
    """A calculator supporting basic and advanced operations."""
    
    def __init__(self, precision: int = 10):
        """Initialize calculator with given decimal precision."""
        self.precision = precision
        self.history: List[str] = []
        self.memory: float = 0.0
    
    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        result = a + b
        self._record(f"{a} + {b} = {result}")
        return result
    
    def subtract(self, a: float, b: float) -> float:
        """Subtract b from a."""
        result = a - b
        self._record(f"{a} - {b} = {result}")
        return result
    
    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers."""
        result = a * b
        self._record(f"{a} * {b} = {result}")
        return result
    
    def divide(self, a: float, b: float) -> float:
        """Divide a by b."""
        if b == 0:
            raise DivisionByZeroError("Cannot divide by zero")
        result = a / b
        self._record(f"{a} / {b} = {result}")
        return result
    
    def power(self, base: float, exponent: float) -> float:
        """Raise base to the power of exponent."""
        result = math.pow(base, exponent)
        self._record(f"{base} ^ {exponent} = {result}")
        return result
    
    def sqrt(self, n: float) -> float:
        """Calculate square root of n."""
        if n < 0:
            raise InvalidInputError("Cannot calculate square root of negative number")
        result = math.sqrt(n)
        self._record(f"sqrt({n}) = {result}")
        return result
    
    def factorial(self, n: int) -> int:
        """Calculate factorial of n."""
        if not isinstance(n, int) or n < 0:
            raise InvalidInputError("Factorial requires non-negative integer")
        if n == 0 or n == 1:
            return 1
        result = 1
        for i in range(2, n + 1):
            result *= i
        self._record(f"{n}! = {result}")
        return result
    
    def average(self, numbers: List[float]) -> float:
        """Calculate average of a list of numbers."""
        if not numbers:
            raise InvalidInputError("Cannot calculate average of empty list")
        result = sum(numbers) / len(numbers)
        self._record(f"avg({numbers}) = {result}")
        return result
    
    def is_prime(self, n: int) -> bool:
        """Check if n is a prime number."""
        if not isinstance(n, int):
            raise InvalidInputError("Prime check requires integer")
        if n < 2:
            return False
        if n == 2:
            return True
        if n % 2 == 0:
            return False
        for i in range(3, int(math.sqrt(n)) + 1, 2):
            if n % i == 0:
                return False
        return True
    
    def fibonacci(self, n: int) -> int:
        """Return the nth Fibonacci number (0-indexed)."""
        if not isinstance(n, int) or n < 0:
            raise InvalidInputError("Fibonacci requires non-negative integer")
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b
    
    def gcd(self, a: int, b: int) -> int:
        """Calculate greatest common divisor of a and b."""
        if not isinstance(a, int) or not isinstance(b, int):
            raise InvalidInputError("GCD requires integers")
        a, b = abs(a), abs(b)
        while b:
            a, b = b, a % b
        return a
    
    def lcm(self, a: int, b: int) -> int:
        """Calculate least common multiple of a and b."""
        if a == 0 or b == 0:
            return 0
        return abs(a * b) // self.gcd(a, b)
    
    def percentage(self, value: float, percent: float) -> float:
        """Calculate percent of value."""
        result = value * (percent / 100)
        self._record(f"{percent}% of {value} = {result}")
        return result
    
    def memory_store(self, value: float) -> None:
        """Store value in memory."""
        self.memory = value
    
    def memory_recall(self) -> float:
        """Recall value from memory."""
        return self.memory
    
    def memory_clear(self) -> None:
        """Clear memory."""
        self.memory = 0.0
    
    def memory_add(self, value: float) -> None:
        """Add value to memory."""
        self.memory += value
    
    def get_history(self) -> List[str]:
        """Return calculation history."""
        return self.history.copy()
    
    def clear_history(self) -> None:
        """Clear calculation history."""
        self.history.clear()
    
    def _record(self, operation: str) -> None:
        """Record an operation to history."""
        self.history.append(operation)


def evaluate_expression(expr: str) -> float:
    """
    Safely evaluate a simple mathematical expression.
    Supports: +, -, *, /, parentheses, and numbers.
    """
    # Remove whitespace
    expr = expr.replace(" ", "")
    
    # Validate characters
    allowed = set("0123456789.+-*/()") 
    if not all(c in allowed for c in expr):
        raise InvalidInputError(f"Invalid characters in expression: {expr}")
    
    # Check balanced parentheses
    depth = 0
    for c in expr:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if depth < 0:
            raise InvalidInputError("Unbalanced parentheses")
    if depth != 0:
        raise InvalidInputError("Unbalanced parentheses")
    
    try:
        # Use eval with restricted globals for safety
        result = eval(expr, {"__builtins__": {}}, {})
        return float(result)
    except ZeroDivisionError:
        raise DivisionByZeroError("Division by zero in expression")
    except Exception as e:
        raise InvalidInputError(f"Invalid expression: {e}")
