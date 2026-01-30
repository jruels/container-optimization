using Microsoft.Data.SqlClient;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

var connectionString = Environment.GetEnvironmentVariable("CONNECTION_STRING")
    ?? "Server=db;Database=master;User Id=sa;Password=YourStrong@Passw0rd;TrustServerCertificate=true;";

app.MapGet("/", () => new { service = "DotNet API", status = "running" });

app.MapGet("/health", async () =>
{
    try
    {
        using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync();
        return Results.Ok(new { status = "healthy", database = "connected" });
    }
    catch (Exception ex)
    {
        return Results.Json(
            new { status = "unhealthy", database = "disconnected", error = ex.Message },
            statusCode: 503
        );
    }
});

app.MapGet("/users", async () =>
{
    try
    {
        using var connection = new SqlConnection(connectionString);
        await connection.OpenAsync();

        // Create table if not exists
        using var createCmd = new SqlCommand(
            "IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Users' AND xtype='U') " +
            "CREATE TABLE Users (Id INT IDENTITY PRIMARY KEY, Name NVARCHAR(100), CreatedAt DATETIME DEFAULT GETDATE())",
            connection);
        await createCmd.ExecuteNonQueryAsync();

        // Insert a sample user
        using var insertCmd = new SqlCommand(
            "INSERT INTO Users (Name) VALUES (@Name); SELECT SCOPE_IDENTITY();",
            connection);
        insertCmd.Parameters.AddWithValue("@Name", $"User_{DateTime.Now.Ticks}");
        var newId = await insertCmd.ExecuteScalarAsync();

        // Get count
        using var countCmd = new SqlCommand("SELECT COUNT(*) FROM Users", connection);
        var count = await countCmd.ExecuteScalarAsync();

        return Results.Ok(new { message = "User created", id = newId, totalUsers = count });
    }
    catch (Exception ex)
    {
        return Results.Json(new { error = ex.Message }, statusCode: 503);
    }
});

Console.WriteLine($"Starting .NET API on port 8080");
Console.WriteLine($"Database connection: {connectionString.Split(';')[0]}");

app.Run("http://0.0.0.0:8080");
