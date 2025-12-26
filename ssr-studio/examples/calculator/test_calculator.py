"""
Tests for the calculator module.
These are the ORIGINAL tests that must continue to pass after bug injection.
"""

import pytest
from calculator import Calculator, CalculatorError, DivisionByZeroError, InvalidInputError, evaluate_expression


class TestBasicOperations:
    """Test basic arithmetic operations."""
    
    def setup_method(self):
        self.calc = Calculator()
    
    def test_add_positive_numbers(self):
        assert self.calc.add(2, 3) == 5
    
    def test_add_negative_numbers(self):
        assert self.calc.add(-2, -3) == -5
    
    def test_add_mixed_numbers(self):
        assert self.calc.add(-2, 5) == 3
    
    def test_subtract_positive_numbers(self):
        assert self.calc.subtract(5, 3) == 2
    
    def test_subtract_negative_result(self):
        assert self.calc.subtract(3, 5) == -2
    
    def test_multiply_positive_numbers(self):
        assert self.calc.multiply(4, 5) == 20
    
    def test_multiply_by_zero(self):
        assert self.calc.multiply(5, 0) == 0
    
    def test_multiply_negative_numbers(self):
        assert self.calc.multiply(-3, -4) == 12
    
    def test_divide_evenly(self):
        assert self.calc.divide(10, 2) == 5
    
    def test_divide_with_remainder(self):
        assert self.calc.divide(7, 2) == 3.5
    
    def test_divide_by_zero_raises_error(self):
        with pytest.raises(DivisionByZeroError):
            self.calc.divide(5, 0)


class TestAdvancedOperations:
    """Test advanced mathematical operations."""
    
    def setup_method(self):
        self.calc = Calculator()
    
    def test_power_positive(self):
        assert self.calc.power(2, 3) == 8
    
    def test_power_zero_exponent(self):
        assert self.calc.power(5, 0) == 1
    
    def test_sqrt_perfect_square(self):
        assert self.calc.sqrt(16) == 4
    
    def test_sqrt_non_perfect(self):
        assert abs(self.calc.sqrt(2) - 1.41421356) < 0.0001
    
    def test_sqrt_negative_raises_error(self):
        with pytest.raises(InvalidInputError):
            self.calc.sqrt(-1)
    
    def test_factorial_zero(self):
        assert self.calc.factorial(0) == 1
    
    def test_factorial_positive(self):
        assert self.calc.factorial(5) == 120
    
    def test_factorial_negative_raises_error(self):
        with pytest.raises(InvalidInputError):
            self.calc.factorial(-1)


class TestStatisticalOperations:
    """Test statistical operations."""
    
    def setup_method(self):
        self.calc = Calculator()
    
    def test_average_integers(self):
        assert self.calc.average([1, 2, 3, 4, 5]) == 3
    
    def test_average_single_value(self):
        assert self.calc.average([42]) == 42
    
    def test_average_empty_raises_error(self):
        with pytest.raises(InvalidInputError):
            self.calc.average([])


class TestNumberTheory:
    """Test number theory operations."""
    
    def setup_method(self):
        self.calc = Calculator()
    
    def test_is_prime_true(self):
        assert self.calc.is_prime(17) is True
    
    def test_is_prime_false(self):
        assert self.calc.is_prime(15) is False
    
    def test_is_prime_two(self):
        assert self.calc.is_prime(2) is True
    
    def test_is_prime_one(self):
        assert self.calc.is_prime(1) is False
    
    def test_fibonacci_zero(self):
        assert self.calc.fibonacci(0) == 0
    
    def test_fibonacci_one(self):
        assert self.calc.fibonacci(1) == 1
    
    def test_fibonacci_ten(self):
        assert self.calc.fibonacci(10) == 55
    
    def test_gcd(self):
        assert self.calc.gcd(48, 18) == 6
    
    def test_gcd_coprime(self):
        assert self.calc.gcd(17, 13) == 1
    
    def test_lcm(self):
        assert self.calc.lcm(4, 6) == 12


class TestMemory:
    """Test memory operations."""
    
    def setup_method(self):
        self.calc = Calculator()
    
    def test_memory_store_recall(self):
        self.calc.memory_store(42)
        assert self.calc.memory_recall() == 42
    
    def test_memory_clear(self):
        self.calc.memory_store(42)
        self.calc.memory_clear()
        assert self.calc.memory_recall() == 0
    
    def test_memory_add(self):
        self.calc.memory_store(10)
        self.calc.memory_add(5)
        assert self.calc.memory_recall() == 15


class TestHistory:
    """Test calculation history."""
    
    def setup_method(self):
        self.calc = Calculator()
    
    def test_history_records_operations(self):
        self.calc.add(1, 2)
        self.calc.multiply(3, 4)
        history = self.calc.get_history()
        assert len(history) == 2
        assert "1 + 2 = 3" in history[0]
    
    def test_clear_history(self):
        self.calc.add(1, 2)
        self.calc.clear_history()
        assert len(self.calc.get_history()) == 0


class TestExpressionEvaluator:
    """Test expression evaluation."""
    
    def test_simple_addition(self):
        assert evaluate_expression("2 + 3") == 5
    
    def test_operator_precedence(self):
        assert evaluate_expression("2 + 3 * 4") == 14
    
    def test_parentheses(self):
        assert evaluate_expression("(2 + 3) * 4") == 20
    
    def test_division(self):
        assert evaluate_expression("10 / 2") == 5
    
    def test_complex_expression(self):
        assert evaluate_expression("((10 + 5) * 2) / 3") == 10
    
    def test_invalid_characters_raises_error(self):
        with pytest.raises(InvalidInputError):
            evaluate_expression("2 + a")
    
    def test_unbalanced_parentheses_raises_error(self):
        with pytest.raises(InvalidInputError):
            evaluate_expression("(2 + 3")
    
    def test_division_by_zero_raises_error(self):
        with pytest.raises(DivisionByZeroError):
            evaluate_expression("5 / 0")
